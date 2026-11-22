# Trách nhiệm dọn tài nguyên của prototype

Trong Spring, bean có scope `prototype` được tạo mới mỗi khi container được yêu cầu cung cấp bean đó. Spring chịu trách nhiệm khởi tạo, tiêm dependency và chạy các callback khởi tạo. Sau khi giao instance cho bên yêu cầu, container không tự động quản lý bước hủy của prototype.

Điểm này rất quan trọng khi một prototype mở file, giữ socket, tạo session hoặc sở hữu tài nguyên cần đóng. **Code nhận instance phải chịu trách nhiệm giải phóng tài nguyên mà instance sở hữu.**

## 1. Vòng đời của prototype kết thúc ở đâu?

Khi Spring tạo một prototype bean, các bước chính vẫn tương tự những scope khác:

1. Spring tạo instance.
2. Container tiêm các dependency và áp dụng các bước xử lý bean.
3. Spring chạy các callback khởi tạo, chẳng hạn `@PostConstruct`, `InitializingBean.afterPropertiesSet()` hoặc `initMethod` được khai báo.
4. Spring trả instance cho thành phần yêu cầu bean.

Sau bước thứ tư, Spring không theo dõi đầy đủ vòng đời sử dụng của instance prototype để tự động gọi callback hủy khi instance không còn được dùng. Vì vậy, khi ApplicationContext đóng, Spring cũng không tự động gọi callback hủy của các prototype đã được cấp trước đó.

Điều này khác với singleton. Với singleton, container quản lý instance trong suốt vòng đời ApplicationContext và có thể gọi các callback hủy khi context đóng. Với prototype, container chỉ quản lý phần tạo và khởi tạo trước khi giao instance cho bên gọi.

## 2. Những callback hủy không tự chạy cho prototype

Các cơ chế sau không được Spring tự động gọi cho một prototype bean chỉ vì bean đó được tạo từ container:

- Phương thức được đánh dấu `@PreDestroy`.
- `DisposableBean.destroy()`.
- Phương thức hủy được khai báo bằng `@Bean(destroyMethod = "...")`.
- Phương thức `close()` hoặc `shutdown()` được Spring suy luận cho bean có hỗ trợ đóng tài nguyên.

Ví dụ, khai báo sau không làm cho Spring tự gọi `close()` khi prototype hết lượt sử dụng:

~~~java
@Configuration
public class ExportConfiguration {

    @Bean(destroyMethod = "close")
    @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
    ExportSession exportSession() {
        return new ExportSession();
    }
}
~~~

Thuộc tính `destroyMethod` vẫn có ý nghĩa với bean có vòng đời hủy do container quản lý, nhưng không tạo ra cơ chế tự thu hồi cho prototype. Nếu `ExportSession` mở file hoặc giữ kết nối, code sử dụng nó phải gọi phương thức giải phóng phù hợp.

Tương tự, thêm `@PreDestroy` vào một phương thức của prototype không thay thế được trách nhiệm đó:

~~~java
@PreDestroy
public void cleanup() {
    // Không được Spring tự động gọi cho prototype.
}
~~~

Không nên dựa vào việc ApplicationContext đóng để giải phóng tài nguyên của prototype.

## 3. Chủ sở hữu instance phải giải phóng tài nguyên

Một cách rõ ràng là để prototype triển khai `AutoCloseable` hoặc `Closeable`, sau đó dùng try-with-resources tại nơi lấy instance.

Ví dụ, mỗi `ExportSession` mở một file để ghi dữ liệu:

~~~java
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.UUID;

import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Scope;
import org.springframework.stereotype.Component;

@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class ExportSession implements AutoCloseable {

    private final BufferedWriter writer;

    public ExportSession(
            @Value("${app.export.directory}") String directory)
            throws IOException {

        Path output = Path.of(
                directory,
                UUID.randomUUID() + ".txt"
        );

        this.writer = Files.newBufferedWriter(
                output,
                StandardCharsets.UTF_8,
                StandardOpenOption.CREATE_NEW,
                StandardOpenOption.WRITE
        );
    }

    public void write(String content) throws IOException {
        writer.write(content);
        writer.newLine();
    }

    @Override
    public void close() throws IOException {
        writer.close();
    }
}
~~~

Mỗi lần container cung cấp `ExportSession`, instance mới được tạo và mở một file riêng. Phương thức `close()` đóng writer, qua đó giải phóng file handle đang được giữ.

Thành phần sử dụng prototype có thể nhận `ObjectProvider` để lấy một instance mới cho từng lần xuất:

~~~java
import java.io.IOException;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;

@Service
public class ExportService {

    private final ObjectProvider<ExportSession> sessions;

    public ExportService(ObjectProvider<ExportSession> sessions) {
        this.sessions = sessions;
    }

    public void export(String content) throws IOException {
        try (ExportSession session = sessions.getObject()) {
            session.write(content);
        }
    }
}
~~~

Trình tự trong phương thức `export()` là:

1. `sessions.getObject()` yêu cầu Spring tạo và trả một prototype instance.
2. `try` sử dụng instance để ghi nội dung.
3. Khi rời khỏi khối `try`, Java tự gọi `session.close()`, kể cả khi thao tác ghi phát sinh exception.
4. Tài nguyên do session sở hữu được giải phóng.

Việc đóng tài nguyên ở đây do Java try-with-resources thực hiện thông qua hợp đồng `AutoCloseable`; Spring không phải gọi destruction callback cho prototype.

Nếu class không triển khai `AutoCloseable`, có thể gọi phương thức giải phóng trong `finally`:

~~~java
ExportSession session = sessions.getObject();
try {
    session.write(content);
} finally {
    session.close();
}
~~~

Try-with-resources thường dễ đọc và ít có nguy cơ bỏ sót cleanup hơn. Nếu phương thức đóng có thể được gọi nhiều lần, class nên định nghĩa rõ hành vi khi đóng lặp; nhiều API tài nguyên đã hỗ trợ cách đóng an toàn này.

## 4. Dùng ObjectProvider để lấy prototype đúng thời điểm

Có một điểm dễ gây nhầm lẫn: tiêm trực tiếp prototype vào một singleton không làm Spring tạo prototype mới mỗi khi singleton gọi một phương thức.

Ví dụ:

~~~java
@Service
public class ExportService {

    private final ExportSession session;

    public ExportService(ExportSession session) {
        this.session = session;
    }

    public void export(String content) throws IOException {
        session.write(content);
    }
}
~~~

Khi Spring tạo singleton `ExportService`, nó cũng lấy một instance `ExportSession` để truyền vào constructor. Instance đó được giữ trong singleton và được dùng lại ở những lần gọi `export()` sau. Nó không tự đổi thành một prototype mới ở mỗi lần gọi.

Nếu yêu cầu nghiệp vụ là mỗi lần xử lý phải có một session riêng, hãy dùng `ObjectProvider<ExportSession>` và gọi `getObject()` tại thời điểm cần tạo session, như ví dụ ở phần trước. Mỗi instance lấy ra cần được đóng bởi thành phần đã nhận quyền sử dụng nó.

`ObjectProvider` giúp trì hoãn việc lấy bean và thể hiện rõ điểm tạo instance. Nó không tự giải phóng prototype sau khi sử dụng; trách nhiệm đóng vẫn thuộc về code gọi.

## 5. Phân biệt tài nguyên sở hữu và dependency dùng chung

Không phải mọi dependency mà prototype tham chiếu đều do prototype sở hữu. Cần phân biệt:

- **Tài nguyên riêng của instance:** file writer do session tự mở, socket riêng hoặc một native handle được cấp riêng. Prototype chịu trách nhiệm đóng hoặc giải phóng.
- **Dependency dùng chung do Spring quản lý:** chẳng hạn một singleton `DataSource`, client dùng chung hoặc service khác được tiêm vào. Prototype không được tự ý đóng dependency dùng chung khi kết thúc công việc.
- **Tài nguyên mượn từ dependency dùng chung:** ví dụ `Connection`, `Statement` và `ResultSet` lấy từ JDBC. Code mở hoặc nhận tài nguyên theo hợp đồng API phải đóng tài nguyên đó đúng cách; đóng một JDBC `Connection` lấy từ pool thường trả kết nối về pool, không đồng nghĩa đóng `DataSource`.

Ví dụ:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
             connection.prepareStatement("select id from orders")) {

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            System.out.println(resultSet.getLong("id"));
        }
    }
}
~~~

Đoạn code đóng `ResultSet`, `PreparedStatement` và `Connection` sau khi dùng. Nó không gọi `dataSource.close()`, bởi `DataSource` là dependency được tiêm và có thể được nhiều thành phần trong ứng dụng sử dụng.

Nguyên tắc cần giữ là: thành phần nào nhận quyền sở hữu một tài nguyên thì thành phần đó phải thực hiện hoặc chuyển giao rõ ràng trách nhiệm giải phóng. Không đóng tùy tiện đối tượng dùng chung chỉ vì một prototype đã kết thúc công việc.

## 6. Tổ chức cleanup khi có nhiều nơi sử dụng prototype

Nếu nhiều service cùng sử dụng một prototype có tài nguyên, mỗi nơi gọi nên tuân theo cùng một hợp đồng đóng. Có thể đặt việc lấy và giải phóng instance sau một phương thức của factory hoặc một component quản lý phiên làm việc để tránh lặp lại quy tắc.

Ví dụ, một phương thức cấp phát và sử dụng session có thể gom cả hai thao tác trong cùng một phạm vi:

~~~java
@Component
public class ExportSessionRunner {

    private final ObjectProvider<ExportSession> sessions;

    public ExportSessionRunner(ObjectProvider<ExportSession> sessions) {
        this.sessions = sessions;
    }

    public void run(ExportWork work) throws IOException {
        try (ExportSession session = sessions.getObject()) {
            work.execute(session);
        }
    }
}
~~~

Trong đó, `ExportWork` là hợp đồng xử lý do ứng dụng định nghĩa:

~~~java
@FunctionalInterface
public interface ExportWork {
    void execute(ExportSession session) throws IOException;
}
~~~

Các thành phần gọi `ExportSessionRunner` chỉ cung cấp công việc cần thực hiện. Runner chịu trách nhiệm tạo session, thực thi và đóng session dù công việc thành công hay thất bại.

Nếu một prototype được trả ra ngoài phạm vi gọi và được sử dụng lâu dài, API trả instance phải quy định rõ bên nhận có trách nhiệm gọi `close()` hay có một component khác giữ quyền sở hữu. Tránh tạo instance có tài nguyên rồi bỏ tham chiếu mà không có điểm cleanup xác định.

## 7. Những lỗi quản lý tài nguyên thường gặp

### Chỉ khai báo @PreDestroy rồi chờ Spring gọi

Với prototype, Spring không tự động gọi callback hủy. Tài nguyên có thể vẫn mở sau khi tác vụ kết thúc. Hãy đưa thao tác giải phóng vào một phương thức rõ ràng như `close()` và gọi phương thức đó tại nơi sở hữu instance.

### Nghĩ rằng đóng ApplicationContext sẽ đóng mọi prototype

Việc đóng context kích hoạt hủy các bean mà container quản lý vòng đời hủy, chẳng hạn singleton. Prototype đã được giao cho code sử dụng không được tự động thu hồi theo cách đó.

### Lấy prototype nhưng không giữ điểm cleanup

Mỗi lần gọi `getBean()` hoặc `ObjectProvider.getObject()` có thể tạo instance mới. Nếu instance mở file hoặc kết nối, việc lấy liên tục mà không đóng sẽ làm tăng số tài nguyên đang được giữ. Hãy ghép thao tác lấy và đóng trong cùng một phạm vi bằng try-with-resources khi có thể.

### Đóng dependency dùng chung

Một prototype có thể nhận singleton dependency qua constructor. Đóng dependency đó trong `close()` của prototype có thể làm hỏng các thành phần khác đang dùng cùng đối tượng. Chỉ giải phóng tài nguyên thuộc quyền sở hữu của instance; tuân thủ hợp đồng của API đối với tài nguyên mượn.

### Cho rằng garbage collector thay thế việc đóng tài nguyên

Garbage collector thu hồi bộ nhớ khi đối tượng không còn được tham chiếu và phù hợp để thu gom. Việc này không bảo đảm file, socket, kết nối hoặc khóa hệ điều hành được giải phóng đúng thời điểm. Không dùng việc đối tượng mất tham chiếu làm chiến lược cleanup.

## 8. Cách xác định trách nhiệm cleanup

Khi thiết kế một prototype bean, hãy trả lời các câu hỏi sau:

1. Instance có tự mở hoặc sở hữu tài nguyên bên ngoài bộ nhớ heap không?
2. API nào dùng để giải phóng tài nguyên đó: `close()`, `release()`, `disconnect()` hay một thao tác chuyên biệt?
3. Thành phần nào lấy instance từ container và chịu trách nhiệm sử dụng nó?
4. Có thể giới hạn việc sử dụng instance trong một khối try-with-resources không?
5. Nếu instance được chuyển cho thành phần khác, hợp đồng chuyển giao quyền sở hữu và cleanup được thể hiện ở đâu?
6. Dependency nào là tài nguyên riêng, dependency nào là đối tượng dùng chung do container quản lý?

Prototype phù hợp với những đối tượng cần instance mới theo yêu cầu, nhưng scope này không đồng nghĩa Spring tự quản lý toàn bộ vòng đời tài nguyên. Container tạo và khởi tạo prototype; code nhận instance quản lý thời gian sử dụng và giải phóng những tài nguyên mà nó sở hữu. Khi ranh giới trách nhiệm được thể hiện bằng `AutoCloseable`, try-with-resources và cách lấy instance đúng thời điểm, ứng dụng sẽ tránh được việc giữ file, socket hoặc kết nối lâu hơn cần thiết.

