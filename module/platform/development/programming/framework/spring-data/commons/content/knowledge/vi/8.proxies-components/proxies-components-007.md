# Interceptor, exception translation và các lớp tích hợp Spring

Một lời gọi repository có thể đi qua nhiều lớp xử lý trước khi tới store: proxy, interceptor, cơ chế giao dịch, điều phối truy vấn hoặc fragment, template và driver. Khi có lỗi, exception còn có thể được chuyển sang hệ phân cấp lỗi truy cập dữ liệu của Spring trước khi quay về ứng dụng.

Spring Data Commons cung cấp hạ tầng repository dùng chung. Module tích hợp store và Spring Framework bổ sung những cơ chế thích hợp để repository tham gia container, giao dịch và xử lý lỗi. Hiểu các ranh giới này giúp giải thích vì sao cùng một phương thức có thể trả kết quả, báo lỗi khi gọi hoặc chỉ báo lỗi ở thời điểm hoàn tất giao dịch.

Bài học thuộc chương **Proxy và thành phần**, tập trung vào interceptor, exception translation và các lớp tích hợp Spring thường gặp. Chi tiết cấu hình và thứ tự advice cần được đối chiếu với module, phiên bản và cách khởi tạo repository thực tế.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt interceptor bao quanh lời gọi với implementation thực hiện phương thức.
- Giải thích vòng đời `proceed`, kết quả và exception trong một chuỗi interceptor.
- Nêu vai trò của `DataAccessException` và `PersistenceExceptionTranslator`.
- Phân biệt tích hợp exception translation qua proxy với cơ chế dịch lỗi bên trong template.
- Xác định nơi phù hợp để xử lý lỗi phát sinh khi gọi, flush, commit hoặc thực thi publisher.
- Nhận ra giới hạn của `@Repository`, `@Transactional`, self-invocation và retry.
- Chọn kiểm tra có ý nghĩa cho những đường thực thi mà ứng dụng thật sự sử dụng.

## 2. Đặt từng thành phần vào đúng vai trò

| Thành phần | Vai trò chính |
| --- | --- |
| Repository interface | Hợp đồng phương thức, domain, ID và kiểu kết quả |
| Repository factory | Tạo hạ tầng thực thi, composition và proxy theo module |
| Interceptor hoặc advice | Xử lý trước, sau hoặc khi lời gọi thất bại; có thể điều phối tiếp |
| Query executor, fragment hoặc base implementation | Thực hiện phương thức được lựa chọn |
| Template, provider, driver | Chuyển thao tác sang công nghệ truy cập dữ liệu cụ thể |
| Transaction manager | Điều phối ranh giới giao dịch của tài nguyên được cấu hình |
| Exception translator | Chuyển lỗi truy cập dữ liệu mà nó nhận biết sang loại lỗi Spring phù hợp |

Một luồng khái quát:

```text
Service hoặc nơi gọi
        |
        v
Repository proxy
        |
        v
Các interceptor/advice được cấu hình
        |
        v
Điều phối phương thức
        +-- query method
        +-- custom fragment
        +-- base implementation
        |
        v
Template / provider / driver / store
```

Sơ đồ chỉ thể hiện các tầng trách nhiệm. Nó không ấn định một thứ tự advice duy nhất cho mọi phiên bản hoặc module. Một ứng dụng còn có thể thêm lớp proxy ở service hoặc các advisor bên ngoài repository proxy.

## 3. Interceptor là một điểm bao quanh lời gọi

Một method interceptor nhận thông tin về phương thức và có thể gọi `proceed()` để chuyển xử lý sang phần kế tiếp trong chuỗi.

Cấu trúc điển hình:

```text
Trước proceed
    -> chuyển lời gọi vào bên trong
        -> nhận kết quả hoặc exception
    -> xử lý sau khi thành công, khi lỗi hoặc khi kết thúc
```

Nếu có hai interceptor A và B với A ở ngoài B:

```text
A: trước
    B: trước
        implementation
    B: sau
A: sau
```

Khi implementation ném exception, exception đi ngược ra qua những interceptor đã tham gia. Mỗi interceptor có thể quan sát, chuyển đổi hoặc truyền tiếp theo trách nhiệm của nó.

Không phải interceptor nào cũng phải gọi `proceed()` trong mọi trường hợp. Một cơ chế có thể từ chối lời gọi hoặc cung cấp kết quả sớm nếu đó là hành vi được thiết kế. Vì vậy, thêm interceptor có thể ảnh hưởng cả kết quả chứ không chỉ ghi log.

### 3.1. Ví dụ đo thời gian bằng `MethodInterceptor`

Đoạn mã sau minh họa vòng đời lời gọi, không tự đăng ký advice vào mọi repository:

```java
import java.util.logging.Logger;

import org.aopalliance.intercept.MethodInterceptor;
import org.aopalliance.intercept.MethodInvocation;

public final class MethodTimingInterceptor implements MethodInterceptor {
    private static final Logger LOG =
            Logger.getLogger(MethodTimingInterceptor.class.getName());

    @Override
    public Object invoke(MethodInvocation invocation) throws Throwable {
        long started = System.nanoTime();
        try {
            return invocation.proceed();
        } finally {
            long elapsed = System.nanoTime() - started;
            LOG.fine(() -> invocation.getMethod().getName()
                    + " completed in " + elapsed + " ns");
        }
    }
}
```

`finally` cho phép quan sát thời gian cả khi phần bên trong ném lỗi. Đoạn mã truyền nguyên kết quả hoặc exception từ `proceed`; nó không biến lỗi thành một kết quả thành công.

Trong một cơ chế đo dùng thật, phần ghi nhận cần được thiết kế để không che exception gốc hoặc làm thay đổi hành vi nghiệp vụ. Dữ liệu đo cũng phải được hiểu theo ranh giới thực thi: thời gian tạo publisher reactive không đồng nghĩa thời gian hoàn tất I/O.

### 3.2. Nhiều interceptor không có nghĩa nhiều fragment cùng chạy

Interceptor là một chuỗi bao quanh lời gọi. Fragment là một thành phần cung cấp implementation cho phương thức.

Một lời gọi có thể qua advice giao dịch và ghi đo, nhưng chỉ chọn một fragment phù hợp để thực hiện phần thân method. Không suy ra rằng mọi fragment có cùng chữ ký sẽ được gọi lần lượt chỉ vì chuỗi interceptor có nhiều bước.

## 4. Những lớp tích hợp thường gặp

Các tên sau giúp đọc tài liệu hoặc stack trace. Chúng không phải danh sách mọi lớp mà ứng dụng phải tự khởi tạo.

| Lớp hoặc hợp đồng | Thuộc vùng trách nhiệm | Ý nghĩa |
| --- | --- | --- |
| `RepositoryFactorySupport` | Hạ tầng repository của Spring Data | Cơ sở cho việc tạo repository và proxy theo module |
| `RepositoryFactoryBeanSupport` | Tích hợp với container | Kết nối việc cấu hình repository với cơ chế `FactoryBean` |
| `RepositoryProxyPostProcessor` | Điểm mở rộng của repository factory | Cho phép tùy chỉnh proxy khi được factory đăng ký |
| `TransactionalRepositoryFactoryBeanSupport` | Tích hợp repository có hỗ trợ tương ứng | Kết nối các thành phần liên quan đến giao dịch và dịch lỗi |
| `TransactionInterceptor` | Spring transaction infrastructure | Áp dụng thuộc tính giao dịch khi lời gọi đi qua advice |
| `PersistenceExceptionTranslator` | Spring data access abstraction | Hợp đồng nhận diện và chuyển đổi exception truy cập dữ liệu |
| `PersistenceExceptionTranslationInterceptor` | Tích hợp exception translation qua lời gọi | Dịch những lỗi phù hợp ở ranh giới được cấu hình |
| `PersistenceExceptionTranslationPostProcessor` | Bean post-processing | Bổ sung tích hợp dịch lỗi cho bean đủ điều kiện, thường liên quan `@Repository` |

Các lớp factory của store xây dựng trên hạ tầng phù hợp với công nghệ đó. Không phải mọi module dùng cùng một tập interceptor hoặc cung cấp cùng giao dịch mặc định.

Ở bên trong còn có xử lý query method, default method và implementation composition. Những chi tiết này cần được xem theo phiên bản khi chẩn đoán sâu; mã nghiệp vụ thường nên phụ thuộc interface công khai thay vì tên lớp proxy hoặc implementation nội bộ.

## 5. Vì sao cần exception translation?

Các công nghệ truy cập dữ liệu có hệ thống exception riêng. Nếu service phải hiểu trực tiếp mọi loại exception của provider, driver và database, nó sẽ gắn chặt với nhiều chi tiết hạ tầng.

Spring cung cấp hệ phân cấp bắt đầu từ `DataAccessException`, là một runtime exception. Exception translation cố gắng biểu diễn loại lỗi truy cập dữ liệu theo các khái niệm chung hơn mà vẫn giữ nguyên nhân bên dưới.

```text
Exception của công nghệ cụ thể
        |
        v
Translator có nhận biết được không?
        |
        +-- có: DataAccessException phù hợp, giữ nguyên nhân
        |
        +-- không: lỗi gốc có thể tiếp tục được truyền ra
```

Việc dịch lỗi không có nghĩa mọi exception đều trở thành cùng một loại. Nó cũng không tự biến một lỗi kỹ thuật thành thông báo nghiệp vụ thích hợp cho người dùng.

### 5.1. Cách hiểu hợp đồng translator

Một translator có phương thức theo ý tưởng:

```java
DataAccessException translateExceptionIfPossible(RuntimeException exception);
```

Kết quả có thể là `null` nếu translator không nhận biết được lỗi. Một mô tả rút gọn bằng Java:

```java
import org.springframework.dao.DataAccessException;
import org.springframework.dao.support.PersistenceExceptionTranslator;

public final class TranslationExample {
    private TranslationExample() {
    }

    public static RuntimeException translatedOrOriginal(
            RuntimeException failure,
            PersistenceExceptionTranslator translator) {

        DataAccessException translated =
                translator.translateExceptionIfPossible(failure);

        return translated != null ? translated : failure;
    }
}
```

Đây là minh họa hợp đồng, không phải yêu cầu ứng dụng dịch lại mọi lỗi mà repository hoặc template đã xử lý. Cơ chế interceptor thật còn có chính sách và ngữ cảnh riêng, chẳng hạn cách xử lý exception được khai báo trên hợp đồng phương thức.

### 5.2. Không phải mọi lỗi đều thuộc phạm vi persistence

Một `IllegalArgumentException` do kiểm tra đầu vào, exception quy tắc miền hoặc lỗi lập trình tùy ý không tự trở thành `DataAccessException` chỉ vì xảy ra trong một lớp repository.

Translator chỉ có thể chuyển những loại lỗi mà nó biết cách ánh xạ. Với lỗi không thuộc trách nhiệm, việc truyền nguyên lỗi có thể là hành vi đúng.

## 6. Đọc hệ phân cấp lỗi theo ý nghĩa

| Loại lỗi Spring thường gặp | Ý nghĩa để bắt đầu phân tích | Điều chưa thể kết luận chỉ từ tên loại |
| --- | --- | --- |
| `DataIntegrityViolationException` | Một ràng buộc toàn vẹn dữ liệu bị vi phạm theo ánh xạ của công nghệ | Luôn là trùng email hoặc cùng một ràng buộc |
| `DuplicateKeyException` | Lỗi trùng khóa được ánh xạ tới loại này | Mọi module đều dùng đúng subtype này cho mọi unique violation |
| `OptimisticLockingFailureException` | Phát hiện xung đột theo cơ chế optimistic locking liên quan | Chỉ cần gọi lại save trên trạng thái cũ là đúng |
| `IncorrectResultSizeDataAccessException` | Số kết quả không phù hợp kỳ vọng của thao tác | Dữ liệu không tồn tại và dữ liệu có quá nhiều kết quả là một trường hợp |
| `DataAccessResourceFailureException` | Tài nguyên truy cập dữ liệu gặp lỗi nghiêm trọng theo cơ chế ánh xạ | Chắc chắn chưa có bất kỳ thay đổi nào được ghi |
| `QueryTimeoutException` | Truy vấn vượt giới hạn thời gian theo khả năng phát hiện và dịch lỗi | Mọi lần thử lại đều an toàn hoặc chắc chắn sẽ thành công |

Các loại cụ thể phụ thuộc module và công nghệ. Cùng một yêu cầu nghiệp vụ có thể cần kiểm tra nhiều ánh xạ hợp lệ thay vì chỉ bắt một subtype rất hẹp.

`Optional.empty()` khi `findById` không tìm thấy là kết quả bình thường theo hợp đồng, không phải một lỗi truy cập dữ liệu bắt buộc phải ném.

Tương tự, truy vấn đơn kết quả có nhiều bản ghi khớp là vấn đề khác với không tìm thấy. Không nên chuyển mọi trường hợp thành một thông báo “không có dữ liệu”.

## 7. Exception translation có thể diễn ra ở nhiều ranh giới

### 7.1. Tích hợp của repository factory

Repository do Spring Data tạo có thể được factory của module bổ sung cơ chế giao dịch và dịch lỗi phù hợp. Ứng dụng không phải tự gắn `@Repository` lên mọi repository interface để thay thế cơ chế này.

Tập post-processor và interceptor thực tế phụ thuộc cách repository được tạo. Nếu tự xây dựng factory hoặc thay một phần hạ tầng, cần hiểu những tích hợp nào còn được đăng ký.

### 7.2. DAO tùy chỉnh có `@Repository`

Một lớp DAO được đánh dấu `@Repository` có thể được cơ chế `PersistenceExceptionTranslationPostProcessor` áp dụng translation khi có hạ tầng và translator phù hợp.

Annotation là một dấu hiệu cho cơ chế tích hợp, không tự thực hiện toàn bộ dịch lỗi mà không cần container hoặc các thành phần hỗ trợ. Một object tạo bằng `new` không tự trở thành bean đã được post-process.

### 7.3. Template tự xử lý lỗi theo công nghệ

Các template như `JdbcTemplate` hoặc `MongoTemplate` có cơ chế xử lý và chuyển lỗi trong đường thao tác của chúng. Vì vậy, translation không phải lúc nào cũng chỉ xuất phát từ một advice bao quanh DAO.

Một DAO không đi qua proxy nhưng sử dụng template vẫn có thể nhận `DataAccessException` từ template. Ngược lại, một DAO gọi thẳng driver không tự có cùng hành vi chỉ nhờ tên lớp hoặc package.

| Đường thực thi | Nơi cần xem cơ chế dịch lỗi |
| --- | --- |
| Bean repository Spring Data | Factory, interceptor và hạ tầng store phía dưới |
| DAO tùy chỉnh do container quản lý | Post-processor, annotation và translator phù hợp |
| Lời gọi template | Cơ chế xử lý exception bên trong template |
| Lời gọi raw provider/driver | API công nghệ và tích hợp mà ứng dụng thực sự sử dụng |

Không cần bọc lại `DataAccessException` nhiều lần chỉ để “đồng nhất lỗi”. Hãy giữ nguyên thông tin nguyên nhân và chỉ chuyển sang exception nghiệp vụ khi có ý nghĩa rõ ràng.

## 8. Thời điểm lỗi quan trọng như loại lỗi

Một thao tác có thể chưa thực hiện toàn bộ I/O vào thời điểm phương thức Java trả về. Phải xác định công việc thật sự diễn ra ở đâu trước khi đặt `try/catch`.

### 8.1. Lỗi ngay trong lời gọi đồng bộ

Nếu driver hoặc template ném lỗi trong lúc repository đang thực thi, interceptor ở ngoài đường đó có cơ hội quan sát và dịch lỗi phù hợp.

```text
repository method
    -> thao tác store
    -> lỗi
    <- translation nếu cơ chế áp dụng
<- exception tới nơi gọi
```

### 8.2. Lỗi khi flush hoặc commit

Với JPA, một thao tác thay đổi trạng thái có thể chưa dẫn đến mọi kiểm tra database ngay trong lần `save`. Lỗi ràng buộc có thể xuất hiện khi flush hoặc hoàn tất giao dịch.

Ví dụ cần phân tích:

```java
try {
    repository.save(customer);
} catch (DataIntegrityViolationException ex) {
    // Xử lý lỗi mà lời gọi này thực sự ném ra.
}
```

Khối `catch` này chỉ bao quanh lần gọi `save`. Nếu giao dịch bên ngoài commit sau khi phương thức service kết thúc, một lỗi commit có thể xuất hiện sau khi khối `catch` đã đi qua.

`saveAndFlush`, nếu module cung cấp, có thể làm một số lỗi xuất hiện sớm hơn. Nó không bảo đảm mọi lỗi chỉ có thể xảy ra ở flush và cũng không thay thế commit.

### 8.3. Lỗi giao dịch không nhất thiết đi qua cùng interceptor repository

Nếu service sở hữu một giao dịch dài hơn lời gọi repository, phần commit có thể được transaction interceptor và transaction manager của service thực hiện sau đó.

Khi ấy interceptor repository đã trả về và không phải nơi quan sát mọi lỗi xảy ra về sau. Transaction manager hoặc hạ tầng ORM có thể có cơ chế chuyển đổi lỗi riêng.

Do đó, muốn xử lý lỗi của toàn bộ nghiệp vụ, cần đặt ranh giới bắt lỗi phù hợp với ranh giới hoàn tất công việc, không chỉ với vị trí dòng `save`.

## 9. Chuyển lỗi kỹ thuật sang lỗi nghiệp vụ có chủ đích

Giả sử đăng ký khách hàng yêu cầu email duy nhất. Không phải mọi `DataIntegrityViolationException` đều có nghĩa email đã được dùng: có thể là ràng buộc `NOT NULL`, khóa ngoại hoặc một điều kiện khác.

Một thiết kế xử lý cần xác định:

1. Ràng buộc nào thể hiện tính duy nhất của email.
2. Cách module/store ánh xạ lỗi từ ràng buộc đó.
3. Thời điểm lỗi có thể xuất hiện: thao tác, flush hay commit.
4. Nơi chịu trách nhiệm chuyển nó thành phản hồi nghiệp vụ.
5. Nguyên nhân kỹ thuật được giữ lại để chẩn đoán như thế nào.

Một cấu trúc có thể dùng khi phù hợp là:

```text
Thành phần xử lý kết quả nghiệp vụ
    -> gọi bean thực hiện giao dịch
        -> ghi dữ liệu
        -> hoàn tất giao dịch ở ranh giới được thiết kế
    <- nhận thành công hoặc lỗi của ranh giới đó
    -> phân loại lỗi đã biết và chuyển thành phản hồi nghiệp vụ
```

Cấu trúc này chỉ bao phủ được lỗi commit tại điểm đó nếu giao dịch cần quan sát thật sự được hoàn tất trước khi lời gọi bên trong trả về. Nếu lời gọi chỉ tham gia một giao dịch còn kéo dài ở ngoài, phải xem lại vị trí xử lý.

Không nên bắt mọi `DataAccessException` rồi trả thành công hoặc trả “khách hàng đã tồn tại”. Một lỗi kết nối có ý nghĩa khác lỗi duy nhất; trạng thái kết quả ghi còn có thể cần được xác minh.

Khi tạo exception nghiệp vụ, nên giữ cause thay vì chỉ lấy `getMessage()` rồi mất chuỗi nguyên nhân. Thông điệp phản hồi và dữ liệu phục vụ chẩn đoán là hai nhu cầu cần được tổ chức rõ.

## 10. Giao dịch, rollback và self-invocation

### 10.1. Exception translation không tự mở giao dịch

Dịch lỗi giúp thống nhất cách biểu diễn exception. Nó không tự cung cấp atomicity, isolation, unique constraint hoặc kiểm soát cạnh tranh.

Một repository có lỗi được dịch đúng vẫn có thể được gọi ngoài ranh giới giao dịch mà nghiệp vụ cần. Một giao dịch được tạo đúng cũng không thay thế ràng buộc dữ liệu hoặc quy tắc cập nhật có điều kiện.

Thuộc tính giao dịch mặc định của repository phụ thuộc module và phương thức. Không mặc định mọi derived query, fragment hoặc store đều có cùng hành vi với các phương thức CRUD chuẩn.

### 10.2. Bắt exception không tự làm giao dịch hợp lệ trở lại

Một lỗi bên trong có thể khiến giao dịch bị đánh dấu rollback-only. Nếu service bắt lỗi rồi tiếp tục như thành công, lúc hoàn tất vẫn có thể gặp lỗi hoặc rollback.

Cần xác định hợp đồng của ranh giới giao dịch, chính sách rollback và khả năng tiếp tục sau lỗi theo công nghệ. Không dùng `catch` như một cách mặc định xóa trạng thái thất bại của giao dịch.

### 10.3. Self-invocation trong mô hình Spring AOP dựa trên proxy

Với proxy-based AOP thông thường, một method của target gọi `this.someMethod()` không tự đi lại qua proxy bên ngoài để áp dụng advice cho `someMethod`.

Nếu `someMethod` được gắn `@Transactional`, điều đó có thể làm ranh giới giao dịch service mà người viết mong đợi không được kích hoạt ở lời gọi nội bộ đó.

Đây không có nghĩa mọi truy cập dữ liệu bên trong chắc chắn không có giao dịch: repository hoặc template có thể tham gia các cơ chế khác. Điều cần kiểm tra là ranh giới giao dịch cụ thể ở service.

Khi cần, có thể tách thao tác giao dịch sang một bean riêng được gọi qua proxy, hoặc sử dụng cơ chế giao dịch tường minh phù hợp. Không nên sửa bằng cách tùy ý unwrap repository proxy hoặc gọi implementation nội bộ.

## 11. Reactive: exception có thể xuất hiện sau khi method trả về

Một method reactive thường trả về publisher mô tả công việc. Lỗi I/O có thể được phát thành tín hiệu lỗi khi publisher được subscribe và thực thi.

Ví dụ sau không bao quanh toàn bộ thời gian thực thi publisher:

```java
try {
    Mono<Customer> result = repository.findById(customerId);
    return result;
} catch (DataAccessException ex) {
    // Chỉ bắt exception được ném ngay khi thực hiện đoạn Java này.
}
```

Ví dụ giả định repository reactive trả `Mono` và các dependency tương ứng đã có. Nếu publisher phát lỗi về sau, xử lý cần được đặt trong pipeline phù hợp, chẳng hạn dùng toán tử chuyển hoặc xử lý tín hiệu lỗi.

Điều đó không có nghĩa được phép biến mọi lỗi thành `Mono.empty()`. Một kết quả không tìm thấy và một lỗi truy cập dữ liệu phải được giữ phân biệt theo hợp đồng.

Giao dịch reactive cần cơ chế giao dịch, tài nguyên và ngữ cảnh reactive phù hợp. Không suy ra một transaction interceptor imperative sẽ tự bao phủ toàn bộ publisher chỉ vì method trả về rất nhanh.

Tương tự, interceptor đo thời gian ở phần trước đo thời gian lời gọi Java. Muốn đo thời gian hoàn tất pipeline phải quan sát vòng đời publisher, bao gồm thành công, lỗi hoặc hủy theo mục tiêu đo.

## 12. Tài nguyên và lỗi phát sinh khi đọc lười

Một số API trả stream hoặc kiểu kết quả được tiêu thụ sau khi method ban đầu trả về. Việc duyệt dữ liệu có thể phát sinh I/O và lỗi ở thời điểm tiêu thụ.

Khi module hỗ trợ kiểu kết quả cần đóng, phải quản lý vòng đời tài nguyên đúng cách, chẳng hạn `try-with-resources` với stream thích hợp. Cũng cần xác định ranh giới giao dịch còn tồn tại đến lúc dữ liệu được đọc hay không.

Không mặc định interceptor bao quanh lần tạo stream quan sát được mọi exception xuất hiện khi client duyệt stream sau đó. Điểm phát sinh lỗi và cơ chế dịch lỗi cần được xem theo implementation thực tế.

Đây là cùng một nguyên tắc với reactive: kiểu trả về mô tả công việc hoặc tài nguyên chưa hoàn tất đòi hỏi hiểu vòng đời thực thi, không chỉ chữ ký phương thức.

## 13. Retry và thứ tự advice cần được thiết kế cùng nhau

Một số exception được phân loại là transient có thể gợi ý khả năng thử lại. Điều đó không chứng minh mọi thao tác đều an toàn để lặp.

Cần xem:

- Thao tác có idempotent hoặc có khóa nhận diện yêu cầu lặp không?
- Lần trước có thể đã ghi thành công nhưng phản hồi bị mất không?
- Mỗi lần thử có dùng một giao dịch hợp lệ không?
- Xung đột có yêu cầu đọc và tính lại trạng thái nghiệp vụ không?
- Chính sách giới hạn số lần và thời gian thử lại là gì?

Hai sơ đồ có ý nghĩa khác nhau:

```text
Retry bao quanh ranh giới giao dịch
    -> mỗi attempt đi qua cơ chế mở/hoàn tất giao dịch theo cấu hình

Giao dịch bao quanh retry
    -> nhiều attempt có thể nằm trong cùng giao dịch đã có lỗi
```

Khả năng thật sự tạo giao dịch mới cho mỗi attempt còn phụ thuộc propagation và tài nguyên. Không chỉ đổi thứ tự hai annotation rồi mặc định kết quả đã đúng.

Đặc biệt, optimistic locking thường cần đọc lại dữ liệu và đánh giá lại quy tắc trước khi ghi. Gọi lại `save` trên cùng một trạng thái cũ không phải cách xử lý chung cho mọi xung đột.

## 14. Tùy chỉnh proxy qua điểm mở rộng phù hợp

`RepositoryProxyPostProcessor` là một điểm mở rộng cho repository factory có hỗ trợ tương ứng. Về ý tưởng, nó có thể bổ sung advice khi proxy được tạo.

Cần phân biệt:

- Viết một implementation của hợp đồng mở rộng.
- Đăng ký nó vào đúng factory hoặc cơ chế cấu hình.
- Xác định thứ tự và phạm vi advice.
- Kiểm tra tác động lên kết quả, exception và giao dịch.

Một bean mang tên `MethodTimingInterceptor` không tự được mọi repository factory tìm thấy và gắn vào proxy. Tương tự, chỉ đánh dấu một post-processor tùy chỉnh là component không bảo đảm factory sẽ sử dụng nó nếu cơ chế tích hợp cần đăng ký riêng.

Nếu mục tiêu là quan sát các lời gọi service, một advice ở ranh giới service có thể phù hợp hơn tùy chỉnh repository factory. Nếu mục tiêu là thay thuật toán truy cập dữ liệu, fragment hoặc repository base class có thể là điểm mở rộng rõ nghĩa hơn.

Không phụ thuộc tên lớp proxy, ép kiểu sang implementation base hoặc thay đổi proxy lúc ứng dụng đang chạy chỉ để gọi xuyên qua những cơ chế đã cấu hình. Việc mở rộng cần có ranh giới mà nhóm phát triển có thể hiểu và kiểm tra.

## 15. Kiểm tra tích hợp theo những điều cần bảo đảm

| Tình huống | Bằng chứng cần quan sát |
| --- | --- |
| Thao tác đọc thành công | Kết quả qua proxy đúng hợp đồng, advice không thay đổi ngoài ý muốn |
| Không tìm thấy ID | Kết quả rỗng được giữ đúng, không bị đổi thành lỗi truy cập dữ liệu |
| Vi phạm ràng buộc đã biết | Loại exception và cause đủ để xử lý đúng quy tắc liên quan |
| Lỗi nghiệp vụ trong custom fragment | Không bị biến thành lỗi persistence không phù hợp |
| Lỗi ở flush hoặc commit | Ranh giới xử lý thật sự quan sát được lỗi và không trả thành công giả |
| Giao dịch thất bại | Rollback và trạng thái sau lỗi đúng yêu cầu |
| Reactive phát tín hiệu lỗi | Pipeline quan sát, chuyển hoặc truyền lỗi đúng hợp đồng |
| Có retry | Không lặp dữ liệu nghiệp vụ ngoài ý muốn và giao dịch mỗi attempt phù hợp |

Mock repository có thể kiểm tra nhánh xử lý của service nhưng không xác nhận translator, provider hoặc transaction manager thực tế. Unit test của interceptor có thể kiểm tra `proceed` và truyền lỗi, nhưng không chứng minh nó đã được gắn vào repository bean.

Khi kiểm tra lỗi database, tạo điều kiện lỗi cụ thể theo store thay vì chỉ ném một exception tự tạo rồi kết luận cơ chế translation đang hoạt động.

Với lỗi có thể xuất hiện ở commit, kiểm tra phải thật sự đi tới ranh giới hoàn tất giao dịch cần quan sát. Một test luôn rollback mà không chạm điều kiện phát lỗi có thể chưa kiểm tra đúng giả định.

## 16. Chẩn đoán theo chuỗi nguyên nhân

| Triệu chứng | Điều cần điều tra |
| --- | --- |
| Exception driver đi thẳng ra service | Lời gọi có qua proxy/template dịch lỗi, translator có nhận biết loại lỗi không |
| Có `@Repository` nhưng không thấy translation mong đợi | Bean có do container quản lý, post-processor và translator có được cấu hình không |
| `catch` quanh save không chạy nhưng request vẫn lỗi | Lỗi phát sinh ở flush/commit hoặc thời điểm thực thi muộn |
| Bắt lỗi rồi vẫn gặp lỗi khi kết thúc giao dịch | Trạng thái rollback-only và ranh giới giao dịch bên ngoài |
| Advice ghi đo không chạy | Advice có được đăng ký, lời gọi có đi qua proxy phù hợp không |
| Thời gian reactive trông rất ngắn | Đang đo lúc tạo publisher hay lúc hoàn tất pipeline |
| Retry tạo thêm dữ liệu | Semantics lặp, idempotency và trạng thái lần ghi trước |
| Đổi thứ tự advice làm hành vi khác | Ranh giới transaction, translation, retry và các lớp proxy thực tế |

Khi đọc stack trace, tìm lỗi gốc và ranh giới phát sinh, không chỉ tên exception ngoài cùng. Một lỗi ở service có thể bắt đầu từ constraint của store, từ mapping hoặc từ logic fragment; cách xử lý cần khác nhau.

Giữ cause giúp truy vết được đường này. Chuyển mọi lỗi thành một `RuntimeException` chỉ chứa chuỗi thông báo sẽ làm mất thông tin mà các lớp tích hợp đã cố gắng bảo toàn.

## 17. Tình huống thực hành

Một service đăng ký khách hàng bắt `DataIntegrityViolationException` ngay quanh `repository.save`, trả kết quả thành công nếu đoạn đó không ném lỗi. Sau khi nâng cấp hoặc đổi cách giao dịch, hệ thống có request báo lỗi ở lúc commit mà không đi qua nhánh xử lý email trùng.

Cần phân tích:

1. Service có đang ở trong một giao dịch lớn hơn lời gọi repository không?
2. Ràng buộc email được kiểm tra ở thao tác nào và thời điểm nào?
3. Exception được chuyển đổi ở template, repository interceptor hay transaction manager?
4. Nơi bắt lỗi có thực sự bao quanh ranh giới hoàn tất giao dịch không?
5. Logic nhận diện email trùng có phân biệt được các ràng buộc khác không?
6. Có đoạn nào bắt lỗi rồi tiếp tục trong một giao dịch đã bị đánh dấu thất bại không?

Thiết kế xử lý nên gắn với ranh giới nghiệp vụ cần hoàn tất và loại lỗi đã xác định. Chỉ thêm một `catch` rộng hơn không tự giải quyết thời điểm lỗi hoặc semantics giao dịch.

## 18. Câu hỏi tự kiểm tra

### Câu 1

Một repository có ba interceptor và hai fragment cùng có một method. Có thể kết luận method của cả hai fragment đều chạy không?

**Gợi ý trả lời:** Không. Chuỗi interceptor bao quanh lời gọi khác với việc chọn implementation trong composition. Cần xem cơ chế điều phối phương thức.

### Câu 2

`PersistenceExceptionTranslator` có bắt buộc chuyển mọi `RuntimeException` thành `DataAccessException` không?

**Gợi ý trả lời:** Không. Translator có thể không nhận biết lỗi và không cung cấp bản dịch. Lỗi nghiệp vụ hoặc lập trình cũng không tự thành lỗi persistence.

### Câu 3

Chỉ có `@Repository` trên một object tạo bằng `new` có đủ để áp dụng post-processing của container không?

**Gợi ý trả lời:** Không. Object phải tham gia cơ chế tích hợp phù hợp. Tuy vậy, template mà object sử dụng vẫn có thể tự dịch lỗi trong đường thao tác của template.

### Câu 4

Vì sao một `catch` quanh `save` có thể không bắt lỗi ràng buộc?

**Gợi ý trả lời:** Lỗi có thể xuất hiện khi flush hoặc commit ngoài phạm vi khối `catch`, tùy store, provider và ranh giới giao dịch.

### Câu 5

Một `try/catch` quanh việc nhận `Mono` có bắt mọi lỗi database phát sinh khi subscribe không?

**Gợi ý trả lời:** Không. Lỗi phát thành tín hiệu về sau cần được quan sát và xử lý trong pipeline hoặc ranh giới reactive phù hợp.

### Câu 6

Bắt exception có làm giao dịch rollback-only trở lại thành công không?

**Gợi ý trả lời:** Không có bảo đảm như vậy. Phải kiểm tra trạng thái và chính sách giao dịch; việc hoàn tất vẫn có thể rollback hoặc báo lỗi.

### Câu 7

Vì sao chỉ thấy `DataIntegrityViolationException` chưa đủ để trả thông báo email trùng?

**Gợi ý trả lời:** Loại lỗi này bao phủ nhiều ràng buộc. Cần nhận diện đúng ràng buộc hoặc nguyên nhân mà nghiệp vụ muốn chuyển đổi.