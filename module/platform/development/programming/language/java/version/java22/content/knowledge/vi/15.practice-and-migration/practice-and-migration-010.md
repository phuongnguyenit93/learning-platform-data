# Chuyển khỏi JDK 22 sang JDK được hỗ trợ, thay API preview bằng bản chính thức khi có

## 1. Đích đến của một lần nâng cấp

Nâng cấp một ứng dụng đang dùng JDK 22 cần đồng thời giải quyết hai việc:

- Đưa ứng dụng sang một bản phân phối JDK còn nhận cập nhật theo chính sách hỗ trợ đã chọn.
- Chuyển những chỗ dùng tính năng/API preview sang hình thức chính thức nếu nền đích đã có.

Việc đổi `JAVA_HOME` mới chỉ thay một thành phần của môi trường. Source, thư viện, compiler, JVM chạy test, runtime đóng gói và lệnh khởi động đều cần phù hợp với nhau.

Trong chương Vận dụng và nâng cấp của module Java 22, bài này chọn **JDK 25 làm nền đích minh họa**. Đây là nền đã có nhiều tính năng chính thức giúp tiếp tục sử dụng các kiến thức hữu ích từng được học ở Java 22. Các trạng thái API trong bài được đối chiếu theo **Java 25**, không được suy diễn thành trạng thái của mọi JDK về sau.

Sau bài học, người học có thể:

1. Xác định “JDK được hỗ trợ” theo nhà phân phối và kênh cập nhật.
2. Lập danh sách tính năng preview, dependency và cấu hình cần xử lý.
3. Phân biệt trường hợp đã chính thức, đã bị rút và chưa có bản chính thức trên nền đích.
4. Chuyển mã sang API đích và biên dịch lại artifact.
5. Kiểm chứng hành vi, triển khai có kiểm soát và chuẩn bị phương án khôi phục phù hợp.

Bài chỉ trình bày mã triển khai dùng tính năng chính thức; tên API preview cũ được nhắc để nhận diện chỗ cần chuyển.

## 2. Chọn một JDK được hỗ trợ

### 2.1. Hỗ trợ gắn với bản phân phối và chính sách cập nhật

Theo roadmap của Oracle, Java 22 thuộc nhóm non-LTS đã bị các feature release sau thay thế; Java 25 là một bản LTS. Các mốc hỗ trợ thương mại trong roadmap áp dụng cho Oracle JDK và đối tượng được mô tả tại đó. Không dùng chúng làm cam kết chung cho mọi bản phân phối OpenJDK. [Oracle Java SE Support Roadmap](https://www.oracle.com/java/technologies/java-se-support-roadmap.html).

Khi chọn JDK đích cho một dự án, cần ghi lại:

| Thông tin | Ví dụ quyết định cần có |
|---|---|
| Nhà phân phối | Bản phân phối được tổ chức lựa chọn và duy trì |
| Feature release | Java 25 trong kịch bản của bài |
| Bản cập nhật | Build cập nhật cụ thể đã được kiểm chứng |
| Nền tảng | Hệ điều hành, kiến trúc CPU và môi trường container |
| Nguồn nhận cập nhật | Kho package, image hoặc kênh phát hành đã chọn |
| Chính sách hỗ trợ | Lịch cập nhật và thời hạn phù hợp với vòng đời sản phẩm |

Một file JDK vẫn tải được từ kho lưu trữ chưa chứng minh nó còn nhận các bản cập nhật cần thiết. Tương tự, nhãn “LTS” chưa thay thế việc xác nhận kênh cập nhật của bản phân phối.

Bài dùng JDK 25 để minh họa lộ trình ổn định. Khi áp dụng về sau, đối chiếu lại roadmap của nhà phân phối tại thời điểm triển khai.

### 2.2. Vì sao nền đích của ví dụ là Java 25?

Java 25 chứa API Scoped Values chính thức, cùng Stream Gatherers và Class-File API đã chính thức từ Java 24. Các tính năng ngôn ngữ như flexible constructor bodies và compact source files cũng đã chính thức ở Java 25. Nhờ vậy, một nhóm có thể giữ nhiều ý tưởng hữu ích của Java 22 và loại bỏ phần phụ thuộc preview tương ứng.

Nếu tổ chức chọn một release khác còn được hỗ trợ, phải lập lại bảng đối chiếu theo release đó. Ví dụ, chọn Java 21 là một quyết định khác về nền tính năng: những tính năng chỉ chính thức từ Java 22 không tự trở thành tính năng chính thức Java 21.

## 3. Kiểm kê trước khi sửa mã

### 3.1. Chụp lại cấu hình hiện tại

Trước khi nâng cấp một ứng dụng thực tế, thu thập một bộ thông tin có thể tái tạo:

| Nhóm | Cần biết |
|---|---|
| Source | Tính năng ngôn ngữ và API preview đang được sử dụng |
| Build | JDK compiler, release đích, plugin và annotation processor |
| Test | JVM thực sự chạy unit test, integration test và tác vụ tùy biến |
| Dependency | Phiên bản được resolve, kể cả phụ thuộc bắc cầu |
| Launch | Cờ JVM trong script, service, container và IDE |
| Artifact | JAR phát hành, image, runtime image hoặc bộ cài |
| Hành vi | Kết quả nghiệp vụ, độ trễ, bộ nhớ, thời gian khởi động và cảnh báo hiện có |

Một manifest của kế hoạch nâng cấp có thể mô tả:

~~~text
Hiện trạng
  source có ScopedValue preview và Stream Gatherers preview
  compiler/runtime phát hành: JDK 22
  lệnh khởi động có --enable-preview

Đích
  compiler/runtime phát hành: JDK 25 theo bản phân phối đã chọn
  release sản phẩm: 25
  dùng ScopedValue và Gatherers chính thức
  không còn phụ thuộc preview trong sản phẩm của ví dụ
~~~

Không ghi “đã bỏ preview” chỉ vì không còn nhìn thấy cờ trong một file build. Cờ có thể được thêm từ profile, biến môi trường, cấu hình IDE hoặc một tác vụ chạy test riêng.

### 3.2. Tìm cả tên cũ lẫn nơi quyết định JVM

Các dấu vết đáng kiểm tra trong dự án gồm:

- `--enable-preview` trong cấu hình compile, test và launch.
- `ScopedValue`, `Gatherer`, `Gatherers`, `java.lang.classfile`.
- `StructuredTaskScope` và module `jdk.incubator.vector`.
- String Templates cùng các lớp/processor từng phục vụ tính năng đó.
- `JAVA_HOME`, toolchain, `maven.compiler.release` hoặc `options.release`.
- `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS`, `JDK_JAVAC_OPTIONS` và cấu hình JVM của công cụ build.
- Agent, mocking, coverage, generated code và công cụ thao tác bytecode.

Kết quả kiểm kê nên gắn mỗi hạng mục với một người chịu trách nhiệm và một tiêu chí xác nhận. Ví dụ: “dependency coverage phải nhận diện được class file của Java 25” cụ thể hơn “cập nhật các thư viện”.

## 4. Phân loại tính năng từng gặp trong Java 22

Bảng sau đối chiếu **nền đích Java 25**. Các dòng chưa có bản chính thức giúp quyết định loại phụ thuộc; bài không hướng dẫn tiếp tục triển khai API thử nghiệm cũ.

| Hạng mục ở Java 22 | Trạng thái trên nền Java 25 | Hướng chuyển |
|---|---|---|
| Scoped Values preview | Chính thức từ Java 25 | Chuyển sang chữ ký API chính thức và biên dịch lại |
| Stream Gatherers preview | Chính thức từ Java 24 | Dùng API chính thức và kiểm tra hành vi pipeline |
| Class-File API preview | Chính thức từ Java 24 | Đối chiếu API mới, kiểm tra parse/transform/generate bytecode |
| Statements before `super(...)` preview | Flexible Constructor Bodies chính thức từ Java 25 | Dùng quy tắc constructor của bản chính thức |
| Implicitly declared classes và instance main preview | Compact source files và instance main chính thức từ Java 25 | Rà lại hình thức source, main và API I/O |
| String Templates preview | Đã bị rút; không có bản chính thức trong Java 25 | Chọn cách tạo chuỗi hoặc API chuyên biệt theo yêu cầu |
| Structured Concurrency preview | Vẫn là preview trong Java 25 | Không coi đã ổn định chỉ vì ScopedValue đã chính thức |
| Vector API incubator | Vẫn là incubator trong Java 25 | Đánh giá lại nhu cầu; không xem đây là API chuẩn ổn định |
| Foreign Function & Memory API | Đã chính thức từ Java 22 | Giữ ý tưởng/API còn phù hợp, kiểm tra tích hợp native trên nền mới |
| Unnamed variables và patterns | Đã chính thức từ Java 22 | Tiếp tục dùng mà không cần preview cho tính năng này |

Nguồn đối chiếu: [ScopedValue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.html), [Gatherers](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Gatherers.html), [ClassFile](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/classfile/ClassFile.html), [các thay đổi ngôn ngữ theo release](https://docs.oracle.com/en/java/javase/25/language/java-language-changes-release.html), [StructuredTaskScope Java 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html), [Vector module Java 25](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.incubator.vector/module-summary.html), [Foreign Function & Memory API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/package-summary.html).

Bảng này tạo ra ba quyết định khác nhau:

1. **Đã có bản chính thức:** chuyển mã và kiểm chứng theo API đích.
2. **Đã bị rút:** thay thiết kế phù hợp với nhu cầu thực tế.
3. **Chưa chính thức trên nền đích:** chọn API chính thức thay thế khi đáp ứng được yêu cầu, hoặc quản lý phần thử nghiệm như một ngoại lệ riêng.

Một sản phẩm đặt mục tiêu không dùng preview/incubator cần xử lý cả nhóm thứ ba. Chỉ đổi sang JDK 25 chưa hoàn tất mục tiêu đó.

## 5. Phân biệt chạy lại artifact và biên dịch lại source

### 5.1. Artifact chính thức có thể được thử trên runtime mới

Với artifact không phụ thuộc preview, thử chạy trên JDK đích là một bước hữu ích để phát hiện sớm lỗi dependency, tùy chọn JVM và thay đổi hành vi. Tài liệu migration của Oracle khuyến nghị kết hợp việc chạy thử, cập nhật thư viện, biên dịch và phân tích dependency. [Preparing for Migration](https://docs.oracle.com/en/java/javase/25/migrate/preparing-migration.html).

Tuy nhiên, việc khởi động thành công chưa kiểm chứng các đường chạy nạp muộn, kết nối native, job nền hoặc tính năng chỉ được bật ở production.

### 5.2. Class file phụ thuộc preview cần xử lý khác

Class file được đánh dấu phụ thuộc preview gắn với đúng release tương ứng. Bật `--enable-preview` trên một runtime mới không cho phép nạp tùy ý class file preview của release cũ. [Ràng buộc preview trong JVM Specification](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-1.html#jvms-1.5.1).

Ví dụ, một class file mang dấu phụ thuộc preview Java 22 không thể được biến thành class file chính thức Java 25 chỉ bằng cách đổi lệnh launch. Cần có source hoặc phiên bản dependency phù hợp để build lại.

Điều này áp dụng cả với class nằm sâu trong JAR dependency. Một JAR có thể chứa nhiều class với các đặc điểm khác nhau; việc class chứa `main` không có vấn đề chưa đủ để kết luận cả artifact phù hợp.

Đối với mã do nhóm quản lý:

~~~text
Source dùng preview Java 22
           |
           | chuyển theo API/ngôn ngữ chính thức đích
           v
Source dành cho Java 25
           |
           | build lại cùng dependency phù hợp
           v
Artifact đã kiểm chứng trên runtime Java 25
~~~

Đối với thư viện bên ngoài, tìm bản phát hành hỗ trợ nền đích hoặc thay dependency theo nhu cầu; không chỉnh byte đánh dấu phiên bản class file để né lỗi.

## 6. Chuyển Scoped Values và Stream Gatherers

### 6.1. ScopedValue: đối chiếu chữ ký API

Khi mã preview cũ có những lời gọi sau, đối chiếu dạng đích:

| Dấu vết cần chuyển | Dạng API chính thức |
|---|---|
| `ScopedValue.runWhere(key, value, task)` | `ScopedValue.where(key, value).run(task)` |
| `ScopedValue.callWhere(key, value, () -> work())` | `ScopedValue.where(key, value).call(() -> work())` |
| `ScopedValue.getWhere(key, value, supplier)` | `ScopedValue.where(key, value).call(supplier::get)` |
| `carrier.get(supplier)` | `carrier.call(supplier::get)` |
| `carrier.call(callable)` với biến kiểu `Callable` | `carrier.call(callable::call)` |

Các tên ở cột trái chỉ phục vụ nhận diện mã cần hiện đại hóa. Chữ ký đích được mô tả tại [Carrier Java 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.Carrier.html).

`call` hiện nhận `ScopedValue.CallableOp<T, X>`, cho phép mô tả cả kiểu kết quả và ngoại lệ. Với biến `Callable`, method reference thích nghi được lời gọi nhưng vẫn mang hợp đồng ngoại lệ của phương thức được tham chiếu. [CallableOp](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.CallableOp.html).

Đừng thay mọi phương thức có tên `get`. `key.get()` đọc binding hiện hành; `carrier.get(key)` vẫn là API chính thức để đọc ánh xạ của carrier. Hai thao tác này khác với overload preview dùng để chạy supplier.

Sau khi chuyển cú pháp, kiểm tra lại:

- Binding bắt đầu ở đâu và có bao phần xử lý thực sự hay không.
- Context có phù hợp để chia sẻ như dữ liệu bất biến hay không.
- Scope lồng và trường hợp ném ngoại lệ có giữ đúng hợp đồng hay không.
- Callback/executor có vượt khỏi phạm vi ban đầu hay không.

ScopedValue chính thức không làm các executor thông thường tự kế thừa binding của nơi gửi task. Nếu luồng xử lý đổi thread, cần thiết kế việc truyền dữ liệu/context phù hợp.

### 6.2. Gatherers: giữ hợp đồng của pipeline

Với Gatherers, không dừng ở việc import được lớp và bỏ cờ preview. Cần đối chiếu kết quả trên dữ liệu biên và cách thực thi pipeline:

| Loại pipeline | Hành vi cần kiểm chứng |
|---|---|
| Gom thành các cửa sổ | Thứ tự, kích thước và cửa sổ cuối không đủ phần tử |
| Pipeline có trạng thái | Mỗi lần thực thi có trạng thái đúng, không dùng nhầm trạng thái cũ |
| Có short-circuit | Phần tử đầu vào được tiêu thụ đến đâu và tác dụng phụ nào đã xảy ra |
| Chạy song song | Chỉ sử dụng khi gatherer và yêu cầu nghiệp vụ phù hợp |
| Xử lý đồng thời | Giới hạn đồng thời, lỗi, gián đoạn và tài nguyên |

Ví dụ bên dưới chọn `windowFixed`, một operation chính thức từ nền Java 24. API cho phép cửa sổ cuối có ít phần tử hơn kích thước yêu cầu. [Gatherers.windowFixed](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Gatherers.html#windowFixed(int)).

### 6.3. Ví dụ hoàn chỉnh sau khi chuyển

Ví dụ `MigrationDemo.java` dùng đồng thời ScopedValue và Gatherers chính thức trên Java 25:

~~~java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class MigrationDemo {
    private static final ScopedValue<String> REQUEST_ID =
            ScopedValue.newInstance();

    static List<List<String>> createBatches() {
        return Stream.of("book", "pen", "bag")
                .map(item -> REQUEST_ID.get() + ":" + item)
                .gather(Gatherers.windowFixed(2))
                .toList();
    }

    public static void main(String[] args) {
        List<List<String>> batches =
                ScopedValue.where(REQUEST_ID, "req-101")
                        .call(MigrationDemo::createBatches);

        System.out.println(batches);
        System.out.println(
                "request-bound-after=" + REQUEST_ID.isBound());
    }
}
~~~

Trong môi trường thực hành có JDK 25:

~~~shell
javac --release 25 -encoding UTF-8 -d out MigrationDemo.java
java -cp out MigrationDemo
~~~

Kết quả mong đợi:

~~~text
[[req-101:book, req-101:pen], [req-101:bag]]
request-bound-after=false
~~~

Ví dụ không cần `--enable-preview`. Khóa context là private, dữ liệu được bind là `String` bất biến và phần xử lý pipeline chạy đồng bộ trong scope.

Kết quả in ra thể hiện hai hợp đồng cần giữ khi chuyển: mọi phần tử có đúng request ID và binding không còn sau khi operation ngoài hoàn tất. Trong ứng dụng thật, bổ sung ca lỗi và scope lồng nếu những hành vi đó có trong luồng nghiệp vụ.

## 7. Chuyển tính năng ngôn ngữ sang hình thức chính thức

### 7.1. Flexible constructor bodies

Với Java 25, constructor có thể thực hiện công việc phù hợp trước lời gọi constructor tường minh. Các giới hạn đối với đối tượng đang được xây dựng vẫn phải được tuân thủ. [Flexible Constructor Bodies](https://docs.oracle.com/en/java/javase/25/language/flexible-constructor-bodies.html).

Ví dụ `Product.java` chỉ chuẩn hóa và kiểm tra tham số trước `super`:

~~~java
import java.util.Objects;

class NamedItem {
    private final String name;

    NamedItem(String name) {
        this.name = name;
    }

    String name() {
        return name;
    }
}

public class Product extends NamedItem {
    Product(String name) {
        String normalized =
                Objects.requireNonNull(name, "name").strip();

        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("Tên phải có nội dung");
        }

        super(normalized);
    }

    public static void main(String[] args) {
        System.out.println(new Product("  Bút  ").name());
    }
}
~~~

Biên dịch và chạy bằng JDK 25:

~~~shell
javac --release 25 -encoding UTF-8 -d out Product.java
java -cp out Product
~~~

Kết quả mong đợi:

~~~text
Bút
~~~

Khi chuyển constructor phức tạp, đọc quy tắc của bản chính thức và rà thứ tự khởi tạo, truy cập instance cùng ngoại lệ trước/sau lời gọi constructor. Không suy luận rằng “có thể đặt lệnh trước super” nghĩa là mọi lời gọi trên `this` đều hợp lệ tại đó.

### 7.2. Compact source files và instance main

Nếu bài thực hành từng dùng dạng lớp khai báo ngầm của bản preview, đối chiếu lại với compact source files của Java 25. Một ví dụ chính thức `Hello.java` là:

~~~java
void main() {
    IO.println("Sẵn sàng trên Java 25");
}
~~~

Chạy bằng JDK 25:

~~~shell
java Hello.java
~~~

Ở nền này, `IO` thuộc `java.lang`; dùng `IO.println(...)` là dạng gọi rõ ràng. Không mang nguyên các giả định import/I/O của từng bản preview sang mã đích. [Compact Source Files and Instance main Methods](https://docs.oracle.com/en/java/javase/25/language/compact-source-files-instance-main-methods.html).

Một ứng dụng đã có `public static void main(String[] args)` vẫn có thể giữ cấu trúc đó. Việc chuyển khỏi JDK 22 không bắt buộc viết lại mọi entry point thành compact source file.

## 8. Xử lý tính năng bị rút hoặc chưa có bản chính thức

### 8.1. String Templates: chuyển theo mục đích sử dụng

String Templates của Java 22 đã bị rút khỏi Java 23 và không có bản chính thức tương ứng trong Java 25. [Ghi chú trong Java Language Changes](https://docs.oracle.com/en/java/javase/25/language/java-language-changes-release.html).

Với thông báo văn bản đơn giản, có thể chọn API chuẩn còn phù hợp:

~~~java
String orderId = "ORD-101";
long total = 250_000L;

String message = "Đơn %s có tổng %d đồng"
        .formatted(orderId, total);
~~~

`String.formatted` là API tạo chuỗi được định dạng. Nó không mặc nhiên thay thế mọi ngữ nghĩa của một processor từng dùng trong mã preview. [String.formatted](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html#formatted(java.lang.Object...)).

Chọn cách chuyển theo loại dữ liệu:

| Nhu cầu ban đầu | Hướng triển khai |
|---|---|
| Thông báo văn bản | Nối chuỗi, `formatted` hoặc builder phù hợp |
| SQL với dữ liệu đầu vào | Giữ dữ liệu trong tham số của prepared statement |
| JSON | Dùng serializer theo mô hình dữ liệu |
| HTML | Dùng cơ chế template/encoding phù hợp ngữ cảnh |
| Processor tùy biến có validation | Bảo toàn validation trong một API được thiết kế rõ ràng |

Ví dụ minh họa phần đặt tham số SQL, giả định có `Connection connection` hợp lệ và phương thức gọi quản lý `SQLException`:

~~~java
try (var statement = connection.prepareStatement(
        "SELECT status FROM orders WHERE order_id = ?")) {
    statement.setString(1, orderId);

    try (var rows = statement.executeQuery()) {
        while (rows.next()) {
            System.out.println(rows.getString("status"));
        }
    }
}
~~~

Điểm cần giữ là cấu trúc truy vấn cùng tham số dữ liệu, thay vì chỉ cố tái tạo cú pháp nội suy chuỗi. [PreparedStatement](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/PreparedStatement.html).

### 8.2. Structured Concurrency và Vector API

Trên Java 25, Structured Concurrency vẫn là preview và Vector API vẫn là incubator. Chúng không chuyển trạng thái theo ScopedValue.

Nếu sản phẩm của kế hoạch cần dùng hoàn toàn API chính thức:

- Với tác vụ đồng thời, xem xét `ExecutorService`, `Future` và virtual threads khi phù hợp; thiết kế rõ việc chờ, timeout, hủy và xử lý lỗi.
- Với tính toán vector, đánh giá implementation Java thông thường hoặc thư viện được dự án chấp nhận, rồi đo lại hiệu năng và kết quả số học.
- Tách những phần thử nghiệm khỏi đường phát hành yêu cầu ổn định nếu chưa có phương án thay đáp ứng hợp đồng.

Không xem một nhóm lời gọi `submit/get` là bản thay thế tương đương mọi bảo đảm của structured concurrency. Tương tự, thay một phép tính vector bằng vòng lặp cần giữ đúng yêu cầu số học và hiệu năng của bài toán.

## 9. Các hạng mục không được giải quyết chỉ bằng bỏ preview

### 9.1. Class-File API và công cụ bytecode

Class-File API chính thức từ Java 24 cung cấp khả năng parse, transform và generate class file. [ClassFile Java 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/classfile/ClassFile.html).

Khi source cũ dùng API preview, đối chiếu chữ ký của từng operation. Với compiler plugin, agent, coverage hoặc mocking, còn cần kiểm tra phiên bản công cụ có xử lý đúng class file và tính năng ngôn ngữ đích hay không.

Một ứng dụng không import `java.lang.classfile` vẫn có thể thất bại vì agent hoặc thư viện thao tác bytecode chưa phù hợp. Vì thế, kiểm kê cả thành phần được nạp bằng agent và plugin.

Không đổi thư viện bytecode đang hoạt động sang Class-File API chỉ để “dùng tính năng mới” nếu việc đó không thuộc nhu cầu nâng cấp.

### 9.2. FFM, native access và vòng đời tài nguyên

FFM API đã chính thức từ Java 22. Khi nâng runtime, vẫn phải xác nhận thư viện native, ABI, nền tảng, quyền native access và vòng đời `Arena`/`MemorySegment` theo cách ứng dụng sử dụng.

Arena kiểm soát vòng đời vùng nhớ mà nó cấp phát; việc API đã chính thức không loại bỏ trách nhiệm quản lý tài nguyên. [Foreign Function & Memory API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/package-summary.html).

Các tùy chọn như `--enable-native-access` có mục đích riêng. Không xóa chúng chỉ vì đang loại `--enable-preview`. Tương tự, `--add-opens` có thể đang phục vụ một dependency; đánh giá lại nhu cầu sau khi cập nhật thư viện thay vì xóa hàng loạt. [Các tùy chọn java launcher](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html).

### 9.3. Tùy chọn JVM và thay đổi hành vi

Đọc thay đổi tích lũy của các release đi qua, trong ví dụ là Java 23, 24 và 25. Chú ý các API/thành phần đã bị loại bỏ, tùy chọn JVM, tích hợp bảo mật và dữ liệu locale. [Removed Tools and Components](https://docs.oracle.com/en/java/javase/25/migrate/removed-tools-and-components.html).

Chỉ xử lý những mục ứng dụng thực sự dùng. Một danh sách toàn bộ thay đổi của JDK không thay thế được việc xác định ảnh hưởng đến đường chạy cụ thể.

## 10. Quy trình chuyển đổi một dịch vụ

### Bước 1: Cố định phạm vi và thu thập mốc so sánh

Ghi lại artifact, dependency, cấu hình và hành vi của phiên bản hiện tại. Chọn những ca nghiệp vụ quan trọng cùng dữ liệu kiểm chứng có thể tái tạo.

Mốc so sánh nên có các trường hợp lỗi, timeout, hủy và đóng tài nguyên nếu dịch vụ sử dụng chúng. Các lần đo hiệu năng cần cùng tải và điều kiện môi trường đủ tương đồng.

### Bước 2: Chuẩn bị toolchain và dependency cho JDK đích

Chọn bản JDK 25 theo chính sách cập nhật của tổ chức. Xác nhận build tool, test engine, annotation processor, JDBC driver và các agent phù hợp nền đích.

Cập nhật dependency theo tương thích đã xác nhận. Tách thay đổi chức năng không liên quan khỏi phạm vi nâng cấp để dễ giải thích nguyên nhân khi kết quả khác trước.

### Bước 3: Chuyển từng nhóm preview

Đối với mỗi nhóm:

1. Xác định hợp đồng đầu vào, đầu ra, lỗi và vòng đời.
2. Sửa theo API/ngôn ngữ đích.
3. Biên dịch và kiểm chứng hành vi tương ứng.
4. Ghi nhận phần thử nghiệm đã được loại khỏi sản phẩm.

Các mục đã có bản chính thức nên dùng bản chính thức. Các mục bị rút hoặc chưa chính thức cần quyết định riêng như ở mục 8.

### Bước 4: Build lại bằng release phù hợp

Với sản phẩm dùng ScopedValue chính thức trong bài, chọn nền Java 25 cho phần mã đó:

~~~shell
javac --release 25 -encoding UTF-8 -d out MigrationDemo.java
~~~

`--release` ràng buộc cú pháp, API nền tảng và class file đầu ra của source đang biên dịch. Nó không tự chuyển đổi dependency đã có sẵn. [Tài liệu javac](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html).

Trong build thực tế, đồng bộ các mức sau:

| Thành phần | Đích của dịch vụ minh họa |
|---|---|
| Compiler toolchain | JDK 25 theo bản phân phối đã chọn |
| Release của source sản phẩm | `25` |
| JVM chạy test | JDK 25 phù hợp bản phát hành |
| JVM của integration test/job tùy biến | Được xác định rõ, tránh dùng ngầm JDK 22 |
| Runtime image/container/bộ cài | Được xây lại cho nền đích |

Nếu thư viện dùng chung vẫn phải hỗ trợ runtime thấp hơn, tách hợp đồng của thư viện đó khỏi dịch vụ dùng API Java 25. Không đặt release thấp rồi gọi trực tiếp API chính thức chỉ có ở nền cao hơn.

Build lại toàn bộ phần sản phẩm cần phát hành trong môi trường sạch. Không trộn class file còn lại của build preview trước đó vào artifact mới.

### Bước 5: Loại cờ preview sau khi đã loại phụ thuộc

Rà lại cấu hình compiler, JVM chạy test, lệnh launch, IDE, CI, service và container. Khi không còn phụ thuộc preview trong phần sản phẩm, bỏ `--enable-preview` ở các vị trí liên quan và xác nhận build/chạy vẫn thành công.

Một dependency còn dùng preview có thể khiến sản phẩm chưa đạt điều kiện này. Cập nhật hoặc xử lý dependency trước khi đánh dấu hoàn tất.

### Bước 6: Kiểm chứng đúng artifact sẽ triển khai

Chạy bộ kiểm chứng trên JAR/image đã đóng gói, với runtime thực tế sẽ phát hành. Nếu dùng `jlink` hoặc `jpackage`, xây lại runtime image/bộ cài theo kế hoạch.

Kiểm tra một điểm quan sát cho phiên bản runtime thực tế, chẳng hạn `java.version` và `java.home`. Điều này giúp phát hiện trường hợp terminal đã đổi JDK nhưng service vẫn chạy bằng runtime được đóng gói trước đó.

### Bước 7: Triển khai và kiểm tra phương án khôi phục

Triển khai giới hạn trên một phần môi trường trước khi mở rộng, theo quy trình của sản phẩm. So sánh lỗi, độ trễ, bộ nhớ và kết quả nghiệp vụ với tiêu chí đã đặt.

Kế hoạch khôi phục phải xác định **cặp artifact và runtime cùng cấu hình tương thích**. Không hạ riêng JVM xuống Java 22 rồi giữ artifact đã biên dịch cho Java 25.

Giữ phương án khôi phục chỉ phục vụ quá trình triển khai đã định; mục tiêu vận hành sau chuyển đổi vẫn là nền JDK được lựa chọn và duy trì.

## 11. Công cụ phân tích hỗ trợ quyết định

Với một JAR ứng dụng thông thường, có thể dùng các công cụ từ JDK đích:

~~~shell
jdeps --jdk-internals app.jar
jdeprscan --release 25 --for-removal app.jar
~~~

Đây là ví dụ tối thiểu; trong dự án có dependency, cấu hình classpath/module path đầy đủ theo yêu cầu công cụ.

| Công cụ | Hỗ trợ việc gì | Giới hạn cần nhớ |
|---|---|---|
| `jdeps` | Xem dependency ở mức class/package, phát hiện dùng API nội bộ JDK | Không xác nhận mọi hành vi runtime hoặc mọi lời gọi reflection |
| `jdeprscan` | Tìm việc sử dụng API Java SE bị deprecated, có thể lọc nhóm dự kiến loại bỏ | Không báo đầy đủ deprecation của thư viện bên ngoài |
| Compiler JDK đích | Phát hiện lỗi source, chữ ký và API trong môi trường biên dịch đã chọn | Không kiểm chứng thay đổi nghiệp vụ hay toàn bộ JAR bắc cầu |
| Test trên artifact phát hành | Quan sát các đường chạy thực tế được kiểm chứng | Độ tin cậy phụ thuộc phạm vi test và môi trường |

Nguồn: [jdeps](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jdeps.html), [jdeprscan](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jdeprscan.html).

Một cảnh báo giảm đi chưa chứng minh một yêu cầu nghiệp vụ được bảo toàn. Ngược lại, một lỗi nạp dependency có thể xảy ra trước khi tính năng mới của ứng dụng được thực thi. Ghi nhận cả class, module và nguyên nhân gốc khi chẩn đoán.

## 12. Tiêu chí nghiệm thu

Một lần chuyển từ JDK 22 sang nền đích của ví dụ cần có bằng chứng tương ứng:

| Tiêu chí | Bằng chứng nên có |
|---|---|
| Nền JDK có chính sách cập nhật phù hợp | Nhà phân phối, phiên bản và kênh cập nhật được ghi rõ |
| Công cụ build phù hợp | Log cho thấy compiler/toolchain thực tế |
| Source đã chuyển | Các điểm dùng preview có phương án và thay đổi cụ thể |
| Không đánh đồng trạng thái tính năng | Bảng đối chiếu theo đúng nền đích |
| Artifact không còn preview theo mục tiêu | Build và launch không cần cờ preview; dependency liên quan đã được kiểm tra |
| Tính đúng đắn được giữ | Các kết quả nghiệp vụ và tình huống lỗi quan trọng đạt yêu cầu |
| Context/tài nguyên được quản lý đúng | Scope, exception, timeout, hủy và close được kiểm chứng khi có sử dụng |
| Dependency và agent phù hợp | Cả đóng gói lẫn các đường nạp muộn đã được xem xét |
| Hiệu năng được đánh giá | Số đo và ngưỡng chấp nhận có điều kiện so sánh rõ ràng |
| Runtime triển khai đúng | JAR/image thực tế chạy trên nền đã chọn |
| Khôi phục có thể thực hiện | Artifact, runtime và cấu hình của phương án khôi phục tương thích |

Một ghi nhận hoàn tất nên mô tả cụ thể, chẳng hạn: “Dịch vụ được build và kiểm chứng trên JDK 25 của nhà phân phối đã chọn; ScopedValue và Gatherers dùng API chính thức; String Templates đã được thay theo từng mục đích; artifact phát hành không còn phụ thuộc preview”. Tránh chỉ ghi “đã nâng Java”, vì mô tả đó không cho biết những ràng buộc nào thực sự đã được xử lý.
