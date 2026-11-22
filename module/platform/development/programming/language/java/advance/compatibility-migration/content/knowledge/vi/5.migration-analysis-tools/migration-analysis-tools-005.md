
# Phân biệt API đã deprecated, dự kiến xóa và đã bị xóa

Khi nâng cấp JDK hoặc thư viện, thông báo *deprecated* thường là dấu hiệu đầu tiên cho thấy một API cần được xem xét. Tuy nhiên, API đã deprecated vẫn có thể tồn tại và tiếp tục hoạt động; API được đánh dấu *for removal* thể hiện ý định loại bỏ mạnh hơn; còn API đã bị xóa thì không còn nằm trong hợp đồng của phiên bản đích. Ba trạng thái này có ý nghĩa khác nhau đối với mã nguồn, bytecode, dependency và kế hoạch migration.

Nếu đánh đồng chúng, nhóm phát triển có thể xử lý quá sớm những API chưa có kế hoạch xóa, hoặc bỏ sót một API đã bị loại bỏ khiến ứng dụng không biên dịch hay không liên kết được khi chạy. Bài học này tập trung vào cách đọc trạng thái deprecation, tìm bằng chứng bằng công cụ Java và quyết định thời điểm thay thế API.

## 1. Ba trạng thái cần phân biệt

| Trạng thái | Ý nghĩa | API còn trong phiên bản hiện tại không? | Mức ưu tiên migration |
|---|---|---|---|
| Deprecated | API vẫn tồn tại nhưng không còn được khuyến nghị sử dụng | Có, trừ khi tài liệu phiên bản cho biết điều khác | Lập kế hoạch thay thế theo tác động và khuyến nghị |
| Deprecated for removal | API vẫn được đánh dấu deprecated và nhà phát triển nền tảng/thư viện thể hiện ý định loại bỏ | Có thể vẫn còn trong release hiện tại | Ưu tiên cao; chuẩn bị thay thế trước khi nâng cấp tiếp |
| Removed | API đã bị loại bỏ khỏi phiên bản đích | Không còn được cung cấp như trước | Bắt buộc xử lý nếu ứng dụng còn phụ thuộc |

Có thể hình dung vòng đời thường gặp:

~~~mermaid
flowchart LR
    A["API đang được hỗ trợ"] --> B["Deprecated"]
    B --> C["Deprecated for removal"]
    C --> D["Removed"]
    B -. "Có thể tồn tại lâu dài" .-> B
    C -. "Thời điểm phụ thuộc chính sách phát hành" .-> C
~~~

Đây là mô hình khái niệm, không phải lịch trình bắt buộc cho mọi API. Một API có thể chỉ được deprecated mà không bao giờ bị xóa. Một số thư viện có chính sách vòng đời riêng; JDK cũng không cam kết mọi API được deprecated sẽ bị loại bỏ sau một số release cố định.

### 1.1. Deprecated: còn dùng được nhưng không còn được khuyến nghị

Một API được đánh dấu deprecated khi nhà cung cấp cho biết API đó không còn là lựa chọn được khuyến nghị. Lý do có thể gồm:

- Có API mới an toàn, rõ ràng hoặc dễ bảo trì hơn.
- Thiết kế cũ gây khó khăn cho việc mở rộng.
- API không còn phù hợp với kiến trúc hoặc chính sách bảo mật hiện tại.
- API chỉ tồn tại để duy trì tương thích với ứng dụng cũ.
- Tính năng đã được thay bằng một cơ chế khác.

Trong Java, annotation **@Deprecated** đánh dấu API ở cấp class, method, constructor, field hoặc thành phần được phép áp dụng annotation đó.

Ví dụ:

~~~java
public class UserService {
    /**
     * @deprecated Use findUserById instead.
     */
    @Deprecated
    public User find(long id) {
        // Cách triển khai cũ
        return findLegacy(id);
    }

    public User findUserById(long id) {
        return findLegacy(id);
    }
}
~~~

Phương thức find(long) vẫn tồn tại. Mã nguồn cũ vẫn có thể gọi nó, nhưng compiler có thể phát cảnh báo để người phát triển biết nên chuyển sang findUserById(long).

Deprecated không đồng nghĩa với lỗi runtime, không đồng nghĩa API đã bị vô hiệu hóa và cũng không tự tạo ra một thời hạn xóa. Hãy đọc tài liệu API để biết lý do, replacement được đề xuất và các khác biệt về hành vi.

### 1.2. Deprecated for removal: đã có ý định loại bỏ

Từ Java 9, annotation **@Deprecated** có thêm hai thuộc tính:

- **since:** phiên bản mà API bắt đầu được deprecated.
- **forRemoval:** cho biết API có được dự kiến loại bỏ trong một bản phát hành tương lai hay không.

Ví dụ:

~~~java
/**
 * @deprecated Use the replacement API.
 */
@Deprecated(since = "2.4", forRemoval = true)
public void oldOperation() {
    // Cách triển khai cũ
}
~~~

Khi forRemoval = true, API vẫn có thể được gọi trong phiên bản hiện tại, nhưng nhà cung cấp đã thể hiện rõ ý định xóa API ở một release tương lai. Compiler hiện đại có thể phát cảnh báo removal riêng để phân biệt với deprecation thông thường.

Trạng thái này cần được ưu tiên hơn trong kế hoạch migration vì:

- Một lần nâng cấp JDK hoặc thư viện tiếp theo có thể khiến API biến mất.
- Việc trì hoãn thay thế làm tăng số lượng thay đổi phải xử lý cùng lúc.
- Các dependency khác có thể tiếp tục gọi API đó dù source ứng dụng đã được sửa.
- API thay thế có thể khác về tham số, kiểu trả về, exception hoặc hành vi.

Tuy nhiên, forRemoval = true không chỉ ra chính xác API sẽ bị xóa ở phiên bản nào. Không nên tự suy ra “sẽ bị xóa ngay ở release kế tiếp”. Hãy tra tài liệu migration, release note, roadmap hoặc chính sách hỗ trợ chính thức của nhà cung cấp.

### 1.3. Removed: API không còn trong phiên bản đích

Khi API đã bị xóa, phiên bản mới không còn cung cấp class, method, field, constructor hoặc module như trước. Ứng dụng phải được chuyển sang API thay thế, dependency độc lập hoặc phương án kiến trúc khác.

Tác động phụ thuộc vào cách sử dụng:

- Nếu source gọi API đã xóa, compiler có thể báo không tìm thấy class hoặc method.
- Nếu ứng dụng đã được biên dịch trước đó và bytecode còn tham chiếu đến method bị xóa, runtime có thể phát sinh NoSuchMethodError.
- Nếu class bị xóa, quá trình nạp hoặc liên kết có thể gặp NoClassDefFoundError.
- Nếu một module nền tảng bị loại bỏ, ứng dụng có thể thiếu module hoặc package mà trước đây JDK tự cung cấp.
- Nếu API thay thế có hành vi khác, ứng dụng vẫn có thể biên dịch nhưng cần kiểm thử lại nghiệp vụ.

Không nên nhầm lỗi do API bị xóa với lỗi bytecode không tương thích. UnsupportedClassVersionError cho biết JVM không hỗ trợ phiên bản class file; NoSuchMethodError hoặc NoClassDefFoundError thường chỉ ra tham chiếu nhị phân không được đáp ứng ở runtime.

## 2. Annotation và tài liệu deprecation trong Java

### 2.1. Annotation @Deprecated

Annotation cung cấp metadata mà compiler, IDE và công cụ phân tích có thể đọc. Từ Java 9, có thể chỉ rõ thời điểm deprecated và ý định loại bỏ:

~~~java
@Deprecated(since = "9")
public void legacyMethod() {
}

@Deprecated(since = "17", forRemoval = true)
public void oldSecurityHook() {
}
~~~

Ý nghĩa:

| Thuộc tính | Mô tả |
|---|---|
| Không ghi thuộc tính | API deprecated; since mặc định là chuỗi rỗng và forRemoval mặc định là false |
| since = "9" | Ghi nhận API được deprecated từ phiên bản 9 |
| forRemoval = false | Không khai báo ý định loại bỏ |
| forRemoval = true | Đánh dấu API dự kiến bị loại bỏ trong tương lai |

since là thông tin do tác giả API cung cấp. Nó không tự được compiler suy ra từ lịch sử Git hay ngày phát hành. Với thư viện riêng, nhóm cần ghi đúng phiên bản phát hành của chính thư viện.

### 2.2. Javadoc tag @deprecated

Trong Javadoc, tag @deprecated dùng để giải thích cho người sử dụng API biết vì sao API bị deprecated và nên dùng gì thay thế.

Ví dụ:

~~~java
/**
 * Returns the legacy account representation.
 *
 * @deprecated Since 2.4. Use {@link #findAccountById(long)}.
 */
@Deprecated(since = "2.4")
public Account findAccount(long id) {
    return findLegacyAccount(id);
}
~~~

Cần phân biệt:

- Annotation @Deprecated là metadata ở cấp ngôn ngữ/bytecode.
- Javadoc @deprecated là nội dung tài liệu dành cho người đọc API.
- Annotation có thể tồn tại mà Javadoc giải thích rất ít hoặc không đầy đủ.
- Javadoc có thể chứa tag deprecated trong tài liệu cũ nhưng bytecode đang dùng không có annotation tương ứng, chẳng hạn do tài liệu và source không đồng bộ.

Một API tốt nên có cả annotation lẫn lời giải thích trong Javadoc. Tài liệu cần nêu replacement, lý do chuyển đổi và khác biệt quan trọng khi thay thế.

### 2.3. Deprecated trong thư viện riêng

Đối với API do tổ chức tự phát triển, deprecation là một hợp đồng giao tiếp với consumer. Cần xác định rõ:

- Phiên bản thư viện nào bắt đầu đánh dấu deprecated.
- Replacement được giới thiệu từ phiên bản nào.
- API cũ còn hoạt động trong bao lâu.
- API có được dự kiến xóa không.
- Phiên bản nào có thể chứa breaking change.
- Consumer cần thay đổi gì để chuyển đổi.

Ví dụ:

~~~java
/**
 * @deprecated Since 3.2. Use {@link #send(Message, DeliveryOptions)}.
 *             This method is planned for removal in a future major release.
 */
@Deprecated(since = "3.2", forRemoval = true)
public void send(Message message) {
    send(message, DeliveryOptions.defaults());
}
~~~

Không nên đánh dấu forRemoval = true chỉ để khuyến khích người dùng chuyển đổi nếu nhóm chưa có ý định xóa. Metadata sai làm giảm độ tin cậy của cảnh báo và khiến consumer khó lập kế hoạch.

## 3. Cách đọc cảnh báo từ compiler

### 3.1. Cảnh báo deprecation thông thường

Khi source gọi API deprecated, compiler có thể phát cảnh báo. Ví dụ:

~~~java
public class LegacyClient {
    public void execute() {
        UserService service = new UserService();
        service.find(10L); // Phương thức đã deprecated
    }
}
~~~

Có thể bật cảnh báo chi tiết:

~~~bash
javac -Xlint:deprecation -d out src/com/example/*.java
~~~

Tùy phiên bản compiler và cách build, thông báo có thể chỉ ra class hoặc method deprecated đang được sử dụng. Hãy đọc toàn bộ warning để xác định vị trí gọi và loại API.

### 3.2. Cảnh báo removal

Với API được đánh dấu forRemoval = true, compiler hiện đại có thể phát cảnh báo removal. Có thể yêu cầu hiển thị rõ:

~~~bash
javac -Xlint:removal -d out src/com/example/*.java
~~~

Để bật cả hai nhóm cảnh báo:

~~~bash
javac -Xlint:deprecation -Xlint:removal -d out src/com/example/*.java
~~~

Trong hệ thống build, cần kiểm tra cấu hình compiler thực sự được áp dụng cho từng module. Một module có thể dùng JDK khác hoặc có tùy chọn lint khác module còn lại.

### 3.3. Chuyển warning thành lỗi có kiểm soát

Compiler hỗ trợ -Werror để biến warning thành lỗi biên dịch:

~~~bash
javac -Xlint:deprecation -Xlint:removal -Werror -d out src/com/example/*.java
~~~

Không nên bật ngay trên một codebase lớn đang có nhiều warning cũ nếu chưa phân loại baseline. Một cách triển khai an toàn hơn:

1. Thu thập warning hiện tại theo module.
2. Ghi nhận các warning đã tồn tại trước migration.
3. Sửa các API mới bị deprecated hoặc removal.
4. Đặt quy tắc CI để ngăn warning mới xuất hiện.
5. Giảm dần baseline cũ theo từng đợt.

Mục tiêu là làm cho warning có giá trị hành động. Nếu hàng trăm warning cũ bị bỏ qua, một cảnh báo mới về API sắp bị xóa rất dễ bị bỏ sót.

## 4. Công cụ tìm API deprecated trong JDK

### 4.1. jdeprscan

jdeprscan là công cụ đi kèm JDK để phân tích class file và JAR nhằm tìm việc sử dụng các API Java SE đã deprecated. Công cụ hữu ích khi mã nguồn không có sẵn, hoặc cần khảo sát artifact đã biên dịch.

Ví dụ:

~~~bash
jdeprscan --release 17 app.jar
~~~

Lệnh trên yêu cầu công cụ kiểm tra các API deprecated theo release Java 17. Hãy chọn release phù hợp với phiên bản mục tiêu cần khảo sát và kiểm tra các tùy chọn được hỗ trợ bởi JDK đang chạy công cụ.

Để tập trung vào API đã được đánh dấu dự kiến loại bỏ:

~~~bash
jdeprscan --release 17 --for-removal app.jar
~~~

Có thể cung cấp classpath cho dependency cần thiết trong một số trường hợp:

~~~bash
jdeprscan --release 17 --class-path "lib/*" app.jar
~~~

Tên đường dẫn và cú pháp classpath cần điều chỉnh theo hệ điều hành, cấu trúc artifact và shell đang dùng.

Các điểm cần nhớ:

- jdeprscan tập trung vào API Java SE deprecated được biết bởi bộ dữ liệu của JDK/release được chọn.
- --for-removal lọc các API có trạng thái deprecated for removal.
- Công cụ phân tích bytecode tĩnh; không quan sát mọi đường chạy runtime.
- Reflection theo tên, method được tạo động, native code hoặc API riêng của thư viện không nhất thiết được phát hiện.
- Chạy công cụ với một release không có nghĩa nó đã phân tích toàn bộ dependency hoặc mọi class được nạp động của ứng dụng.
- Phiên bản jdeprscan có thể giới hạn các release mà nó hiểu; hãy xem jdeprscan --help và tài liệu của JDK cụ thể.

### 4.2. jdeps không thay thế jdeprscan

Hai công cụ thường được dùng cùng nhau nhưng trả lời những câu hỏi khác nhau:

| Công cụ | Mục tiêu chính | Ví dụ |
|---|---|---|
| jdeprscan | Tìm việc sử dụng API Java SE deprecated | API deprecated hoặc deprecated for removal |
| jdeps | Phân tích phụ thuộc class/package/module | Dependency vào JDK internal API, package hoặc module |

Ví dụ kiểm tra internal API:

~~~bash
jdeps --jdk-internals --recursive app.jar
~~~

Một API nội bộ của JDK không nhất thiết được đánh dấu deprecated. Ngược lại, một API Java SE public có thể bị deprecated nhưng không phải internal API. Vì vậy, kết quả của hai công cụ bổ sung cho nhau.

### 4.3. Tìm API deprecated trong thư viện bên thứ ba

jdeprscan chủ yếu giúp tìm deprecated API của nền tảng Java. Nó không thay thế việc đọc deprecation metadata của các thư viện như Spring, Hibernate, Jackson hoặc thư viện nội bộ của tổ chức.

Với dependency bên ngoài:

- Xem Javadoc và API reference đúng phiên bản.
- Đọc release note và migration guide.
- Kiểm tra annotation @Deprecated trong source hoặc bytecode.
- Dùng IDE hoặc công cụ static analysis có khả năng đọc metadata của dependency.
- Tìm các warning khi compile module gọi API.
- Kiểm tra dependency graph để biết phiên bản nào thực sự được resolve.

Nếu một dependency đã biên dịch sẵn gọi một method deprecated, compiler của ứng dụng không nhất thiết phát warning cho mọi trường hợp. Cần quét bytecode, kiểm tra tài liệu dependency hoặc dùng công cụ phân tích tương ứng.

## 5. Xác định API đã bị xóa giữa các phiên bản

### 5.1. So sánh API theo release

Khi migration từ JDK cũ lên JDK mới, cần xác định API/module nào đã bị loại bỏ trong khoảng phiên bản đó. Các nguồn bằng chứng nên dùng:

- Java SE API Specification của phiên bản nguồn và đích.
- JDK Release Notes.
- JEP mô tả việc deprecated hoặc removal.
- Migration Guide của nhà cung cấp JDK.
- Release note của framework và dependency.
- Báo cáo compile/test trên runtime đích.

Không nên chỉ tìm từ khóa deprecated trong source hiện tại. API đã bị xóa sẽ không còn annotation trong class library đích để tìm. Phải đối chiếu lịch sử và tài liệu giữa hai release.

### 5.2. Ví dụ: Java EE và CORBA modules bị loại khỏi JDK 11

Trước Java 11, một số module Java EE và CORBA từng được phân phối cùng JDK, chẳng hạn:

- java.xml.bind (JAXB).
- java.xml.ws (JAX-WS).
- java.activation.
- java.corba.
- java.se.ee aggregate module.

Các module này đã được loại khỏi JDK 11 theo thay đổi được mô tả trong JEP 320. Ứng dụng cũ có thể từng sử dụng các lớp như javax.xml.bind.JAXBContext mà không khai báo dependency riêng vì JDK cung cấp chúng.

Sau khi chuyển sang JDK 11, ứng dụng có thể gặp lỗi biên dịch kiểu “package ... does not exist” hoặc runtime không tìm thấy class nếu vẫn trông đợi các module đó có sẵn.

Phương án thường là khai báo dependency phù hợp từ hệ sinh thái tương ứng, chọn phiên bản hỗ trợ JDK mục tiêu và kiểm tra namespace/API thực tế. Không nên chỉ thêm một JAR bất kỳ: cần xác minh version, package, transitive dependencies và hành vi runtime.

### 5.3. Ví dụ: Nashorn JavaScript engine

Nashorn được deprecated từ Java 11 và sau đó bị loại khỏi JDK 15 theo JEP 372. Ứng dụng dùng ScriptEngineManager để tìm engine JavaScript có thể không còn nhận được Nashorn từ JDK như trước.

Ví dụ code cũ:

~~~java
import javax.script.ScriptEngine;
import javax.script.ScriptEngineManager;

public class ScriptRunner {
    public Object evaluate(String source) throws Exception {
        ScriptEngine engine =
                new ScriptEngineManager().getEngineByName("nashorn");
        return engine.eval(source);
    }
}
~~~

Nếu engine không có mặt, getEngineByName có thể trả về null. Ứng dụng cần chọn engine thay thế tương thích, ví dụ một implementation JavaScript độc lập được phân phối như dependency, rồi kiểm tra khác biệt về cú pháp, API tích hợp Java, bảo mật và hiệu năng.

Ví dụ này cho thấy removal không phải lúc nào cũng biểu hiện bằng compile error. API tìm engine vẫn có thể tồn tại, nhưng implementation cụ thể đã không còn được JDK cung cấp.

## 6. Ảnh hưởng đến source compatibility và binary compatibility

### 6.1. Source compatibility

Source compatibility trả lời câu hỏi: mã nguồn cũ có thể biên dịch với API và compiler của phiên bản đích hay không?

Nếu method hoặc class đã bị xóa, compiler thường báo lỗi không tìm thấy symbol:

~~~text
error: cannot find symbol
~~~

Để xử lý, cần thay lời gọi bằng API thay thế hoặc bổ sung dependency tương ứng nếu API đã được tách khỏi JDK nhưng vẫn được cung cấp độc lập.

### 6.2. Binary compatibility

Binary compatibility trả lời câu hỏi: bytecode đã biên dịch trước đó có thể liên kết với class library/dependency mới hay không?

Ví dụ ứng dụng đã biên dịch với method:

~~~java
client.oldSend(message);
~~~

Nếu runtime library mới không còn method đó, JVM có thể ném:

~~~text
java.lang.NoSuchMethodError
~~~

Nếu class bị xóa, có thể xuất hiện:

~~~text
java.lang.NoClassDefFoundError
~~~

Nếu module hoặc package không còn được cung cấp, lỗi có thể xuất hiện ở bước compile, resolve module hoặc class loading tùy cách đóng gói.

Do đó, build lại source với JDK mới là bước cần thiết nhưng chưa đủ. Phải kiểm tra toàn bộ dependency runtime và artifact thực tế. Một JAR cũ có thể chứa bytecode tham chiếu đến API đã bị xóa, dù source của ứng dụng chính không còn gọi API đó.

### 6.3. Behavioral compatibility

Ngay cả khi API thay thế có chữ ký tương tự, hành vi có thể khác:

- Giá trị mặc định thay đổi.
- Thứ tự xử lý hoặc quy tắc parse thay đổi.
- Exception được ném ra trong trường hợp trước đây không lỗi.
- Encoding, timezone hoặc locale khác.
- API mới yêu cầu cấu hình hoặc resource bổ sung.
- Engine/provider mới có tập tính năng hoặc giới hạn bảo mật khác.

Vì vậy, việc thay API cần đi kèm regression test trên các trường hợp nghiệp vụ thực tế.

## 7. Phân loại phát hiện để lập kế hoạch migration

Mỗi kết quả nên được phân loại riêng để xác định mức độ khẩn cấp:

| Nhóm phát hiện | Dấu hiệu | Hành động |
|---|---|---|
| Deprecated, không for removal | @Deprecated, forRemoval=false hoặc không khai báo | Ghi nhận replacement, đánh giá chi phí và lập lịch |
| Deprecated for removal | forRemoval=true, cảnh báo [removal] | Ưu tiên thay thế trước khi nâng lên release có khả năng xóa |
| Removed ở JDK đích | API/module không còn trong release đích | Xử lý trước khi build hoặc deploy trên runtime mới |
| Removed khỏi dependency | Class/method không còn trong phiên bản thư viện được resolve | Nâng consumer, giữ version tương thích tạm thời hoặc thay thư viện |
| Deprecated trong dependency riêng | Javadoc/annotation của thư viện cảnh báo | Theo dõi migration guide và chính sách vòng đời của nhà phát hành |
| Không còn implementation/provider | API tìm provider còn nhưng implementation đã biến mất | Thêm provider độc lập hoặc chọn giải pháp thay thế |

Một phát hiện nên kèm:

- Tên API đầy đủ và loại thành phần.
- Phiên bản bắt đầu deprecated, nếu có.
- Giá trị forRemoval và nguồn xác nhận.
- Phiên bản cuối cùng còn API hoặc phiên bản đã xóa.
- Dependency hoặc module chứa API.
- Các call site trong source/bytecode.
- Replacement được khuyến nghị.
- Mức độ thay đổi về chữ ký và hành vi.
- Test cần bổ sung.
- Người hoặc nhóm chịu trách nhiệm.

## 8. Quy trình kiểm tra deprecation/removal

### Bước 1: Xác định phiên bản nguồn và đích

Ghi rõ JDK hiện tại, JDK mục tiêu, phiên bản framework và dependency. Cùng một API có thể được deprecated ở một release, đánh dấu for removal ở release khác và bị xóa ở một release tiếp theo.

### Bước 2: Thu thập cảnh báo compile

Bật lint deprecation/removal cho các module. Lưu warning theo file, class và method. Tách warning từ source của ứng dụng với warning đến từ generated source hoặc module test.

### Bước 3: Quét artifact bằng jdeprscan

Chạy jdeprscan với release mục tiêu và tùy chọn --for-removal để tạo danh sách API Java SE cần chú ý. Nếu có nhiều JAR hoặc module, quét từng artifact cần thiết và cung cấp classpath phù hợp.

### Bước 4: Quét internal API bằng jdeps

Chạy jdeps --jdk-internals để tìm phụ thuộc vào API nội bộ. Đây là một nhóm rủi ro riêng với deprecation, nên lưu báo cáo riêng hoặc phân loại riêng trong danh mục migration.

### Bước 5: Kiểm tra dependency và release notes

Đối chiếu warning với phiên bản dependency được resolve. Đọc migration guide để xác định replacement, phiên bản hỗ trợ JDK mục tiêu và thay đổi cấu hình.

### Bước 6: Kiểm tra API đã bị xóa

So sánh API Specification, release note và JEP giữa source và target. Tìm các package/module không còn được cung cấp và các implementation/provider đã bị loại bỏ.

### Bước 7: Thay thế và kiểm thử

Sửa call site, cập nhật dependency, cấu hình provider và build lại. Chạy unit test, integration test và kiểm thử trên đúng runtime mục tiêu. Đặc biệt kiểm tra những nhánh dùng reflection, service loader, scripting engine hoặc API chỉ được gọi khi chạy một chức năng cụ thể.

### Bước 8: Ngăn phát sinh warning mới

Sau khi xử lý baseline, cấu hình CI để phát hiện warning deprecation/removal mới. Có thể áp dụng -Werror cho các module đã kiểm soát được warning, hoặc dùng quy tắc lint/static analysis tương ứng của build tool.

## 9. Ví dụ: thiết kế vòng đời cho API của thư viện nội bộ

Giả sử thư viện account-client có method cũ:

~~~java
public Account get(long id) {
    return repository.find(id);
}
~~~

Nhóm muốn chuyển sang API mới có tên rõ nghĩa hơn và hỗ trợ tùy chọn truy vấn:

~~~java
public Account findById(long id, QueryOptions options) {
    return repository.find(id, options);
}
~~~

Có thể triển khai theo từng release:

**Release 2.4:** thêm API mới, giữ API cũ và đánh dấu deprecated:

~~~java
/**
 * @deprecated Since 2.4. Use {@link #findById(long, QueryOptions)}.
 */
@Deprecated(since = "2.4")
public Account get(long id) {
    return findById(id, QueryOptions.defaults());
}
~~~

**Release 3.0:** nếu chính sách tương thích cho phép breaking change, đánh dấu API cũ for removal trong một release trước đó hoặc thông báo rõ thời điểm loại bỏ. Nếu API đã được đánh dấu for removal từ 2.4, consumer có thể chủ động chuyển đổi.

**Release 4.0 hoặc release đã công bố:** loại bỏ method cũ theo kế hoạch versioning và migration guide.

Đây chỉ là ví dụ về chính sách thư viện riêng, không phải quy tắc bắt buộc của mọi dự án. Nhóm cần công bố thời gian hỗ trợ, quy tắc semantic versioning và cách xử lý consumer chưa thể nâng cấp.

## 10. Các giới hạn cần nhớ khi đọc kết quả

- Một API deprecated vẫn có thể được hỗ trợ nhiều năm; không tự đặt deadline nếu nhà cung cấp chưa công bố.
- forRemoval=true là tín hiệu ý định, không phải ngày xóa chính xác.
- Một API không còn deprecated có thể đã bị xóa khỏi release đích; tìm warning ở source hiện tại sẽ không phát hiện nó.
- jdeprscan không quét toàn bộ API deprecated của mọi thư viện bên thứ ba.
- jdeps tìm dependency tĩnh, không chứng minh mọi đường chạy runtime.
- Reflection và tên class động có thể không xuất hiện trong kết quả compile hoặc bytecode analysis thông thường.
- Một implementation/provider bị xóa có thể khiến API tra cứu vẫn compile nhưng không tìm thấy provider lúc chạy.
- Build thành công không chứng minh hành vi tương thích.
- Một warning trong test hoặc công cụ build không nhất thiết ảnh hưởng artifact production, nhưng vẫn cần phân loại rõ ràng.
- Không nên xóa API cũ khỏi thư viện riêng trước khi đánh giá consumer và chính sách tương thích đã công bố.

## 11. Checklist trước khi kết luận

### Nhận diện trạng thái

- [ ] Đã phân biệt deprecated, deprecated for removal và removed.
- [ ] Đã kiểm tra annotation @Deprecated, thuộc tính since và forRemoval.
- [ ] Đã đọc Javadoc @deprecated và replacement được đề xuất.
- [ ] Đã xác định trạng thái API theo đúng phiên bản JDK/dependency mục tiêu.
- [ ] Đã xác định API thuộc Java SE, JDK internal hay thư viện bên thứ ba.

### Phân tích công cụ

- [ ] Đã bật -Xlint:deprecation và -Xlint:removal khi phù hợp.
- [ ] Đã quét artifact bằng jdeprscan.
- [ ] Đã chạy jdeprscan --for-removal để tập trung vào API dự kiến xóa.
- [ ] Đã dùng jdeps --jdk-internals cho nhóm API nội bộ.
- [ ] Đã kiểm tra dependency graph và các JAR thực sự có trong runtime.

### Đánh giá migration

- [ ] Đã tìm API/module/provider đã bị xóa giữa hai release.
- [ ] Đã xác định replacement và khác biệt về hành vi.
- [ ] Đã kiểm tra binary compatibility của dependency.
- [ ] Đã cập nhật source, cấu hình và dependency phù hợp.
- [ ] Đã chạy test trên đúng JDK và môi trường triển khai đích.
- [ ] Đã có quy tắc CI để ngăn warning mới không được xử lý.

## Kết luận

Deprecated cho biết API không còn được khuyến nghị; deprecated for removal cho biết nhà cung cấp dự kiến loại bỏ API; removed nghĩa là phiên bản đích không còn cung cấp API đó. Mỗi trạng thái cần cách xử lý và mức ưu tiên khác nhau.

Hãy kết hợp compiler lint, jdeprscan, jdeps, dependency graph, JDK release notes và migration guide để lập danh mục chính xác. Sau khi thay API, cần build lại toàn bộ ứng dụng và kiểm thử trên runtime mục tiêu để xác nhận cả source compatibility, binary compatibility lẫn hành vi. Với API của thư viện riêng, hãy công bố rõ replacement và vòng đời để consumer có đủ thời gian migration.

