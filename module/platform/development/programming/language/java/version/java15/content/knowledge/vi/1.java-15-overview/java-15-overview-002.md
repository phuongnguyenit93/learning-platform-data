# Java 15 — Text Blocks, mã sinh động với Hidden Classes, chữ ký EdDSA và bộ thu gom rác

## Mục tiêu và phạm vi

Bài học thuộc nhóm **Định hướng** của Java 15. Bốn chủ đề dưới đây đã trở thành nền tảng hoặc khả năng sử dụng trong các JDK hiện đại: viết chuỗi nhiều dòng bằng **Text Blocks**, tạo lớp phục vụ mã sinh động bằng **Hidden Classes**, ký và kiểm tra chữ ký với **EdDSA**, và lựa chọn **ZGC/Shenandoah** cho yêu cầu độ trễ GC thấp. Nội dung tập trung vào API, cơ chế và cách vận dụng còn có giá trị hiện nay. Ví dụ dùng Java 15 trở lên, không cần bật preview.

| Chủ đề | Được chuẩn hóa hoặc sẵn sàng sản xuất trong Java 15 | Tình huống áp dụng hôm nay |
| --- | --- | --- |
| Text Blocks (JEP 378) | Cú pháp chuỗi nhiều dòng chính thức | JSON, SQL, HTML, thông báo và mẫu văn bản nhúng trong Java |
| Hidden Classes (JEP 371) | API định nghĩa lớp ẩn từ bytecode | Framework, proxy, lambda và bộ sinh mã khi chạy |
| EdDSA (JEP 339) | Hỗ trợ chữ ký Ed25519/Ed448 trong Java Security | Ký thông điệp, cấu hình, bản phát hành hoặc dữ liệu trao đổi |
| ZGC (JEP 377), Shenandoah (JEP 379) | Hai bộ thu gom rác độ trễ thấp sẵn sàng cho production | Dịch vụ có yêu cầu chặt về độ trễ phản hồi |

**Phân biệt ngay từ đầu:** Text Blocks là cú pháp xử lý `String` trong mã nguồn; Hidden Classes là công cụ runtime cho bytecode; EdDSA là mật mã khóa bất đối xứng; GC quản lý bộ nhớ. Chúng giải quyết bốn bài toán độc lập, dù cùng được nhắc trong Java 15.

## 1. Text Blocks: chuỗi nhiều dòng dễ đọc và dễ bảo trì

### 1.1. Cú pháp, kiểu dữ liệu và kết quả thực tế

Text block bắt đầu bằng ba dấu nháy kép `"""`, sau đó **bắt buộc có xuống dòng**; kết thúc bằng `"""`. Giá trị tạo ra vẫn là đối tượng `String` bình thường: có thể truyền vào API hiện có, gọi `formatted(...)`, `stripIndent()` hay `replace(...)`, không có kiểu chuỗi mới.

**Tệp `TextBlocksDemo.java`** (đã kiểm tra biên dịch bằng `javac --release 15`):

~~~java
public class TextBlocksDemo {
    public static void main(String[] args) {
        String json = """
            {
              "name": "Lan",
              "active": true
            }
            """;

        System.out.println(json.contains("\"name\": \"Lan\""));
        System.out.println(json.endsWith("\n"));

        String line = """
            Java \
            15\
            """;
        System.out.println(line.equals("Java 15"));

        String padded = """
            A\s
            """;
        System.out.println(padded.equals("A \n"));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 15 TextBlocksDemo.java
java TextBlocksDemo
~~~

Kết quả chuẩn:

~~~text
true
true
true
true
~~~

Giải thích từng kiểm tra:

- Dấu nháy kép trong nội dung JSON không cần escape; text block vẫn chứa `"name": "Lan"`.
- Khi dấu đóng `"""` nằm trên một dòng riêng, chuỗi thông thường có ký tự xuống dòng `\n` cuối.
- Dấu `\` ngay trước xuống dòng nguồn nối hai dòng thành một dòng logic; ví dụ tạo đúng `Java 15`.
- `\s` tạo một dấu cách thực, kể cả ở cuối dòng; ví dụ chuỗi bằng `"A \n"`.

### 1.2. Cách trình biên dịch xử lý khoảng trắng

Không nên suy đoán số dấu cách chỉ bằng cách đếm indent của mã Java. Quá trình xử lý text block có các quy tắc quan trọng:

1. Chuẩn hóa dấu xuống dòng nguồn thành `\n`.
2. Loại **indent chung mang tính trình bày** (incidental indentation), dựa vào các dòng và vị trí dấu đóng. Nhờ vậy có thể thụt khối code Java mà không bắt chuỗi giữ toàn bộ indent ấy.
3. Loại các dấu cách ở cuối dòng theo quy tắc của text block, rồi mới diễn giải các escape sequence như `\s` và `\` + xuống dòng.

Ví dụ khi cần giữ đúng số khoảng trắng của một payload, hãy kiểm tra bằng `equals`, `length` hoặc in dấu phân cách; không phụ thuộc vào cách editor hiển thị. Nếu cần giữ dấu cách cuối dòng, thêm `\s`. Nếu không muốn dấu `\n` cuối, đặt dấu đóng ngay sau nội dung thích hợp hoặc dùng một phép biến đổi `String` có chủ đích.

### 1.3. Cách dùng thực tế và ranh giới an toàn

Text Blocks phù hợp cho JSON mẫu, email, SQL nhiều dòng, HTML thử nghiệm, fixture trong unit test:

~~~java
String sql = """
    SELECT id, full_name
    FROM users
    WHERE status = ?
    ORDER BY id
    """;

String message = """
    Xin chào %s,
    Đơn hàng #%s đã được xử lý.
    """.formatted("Lan", "A103");
~~~

Đoạn trên minh họa tạo chuỗi và **không phải chương trình độc lập**. Khi thi hành SQL, truyền giá trị động qua `PreparedStatement` và tham số `?`; text block **không tự** chống SQL injection. Khi tạo JSON chứa dữ liệu người dùng, dùng thư viện serialize JSON để escape ký tự đúng quy tắc, đừng tự ghép chuỗi. Với HTML, cần encode đúng ngữ cảnh trước khi hiển thị dữ liệu chưa tin cậy.

Sai lầm dễ gặp:

- Cho rằng text block tự bỏ mọi `\n` hoặc bảo toàn mọi dấu cách: hãy xem vị trí dấu đóng và các escape.
- Cho rằng text block thay thế template engine/JSON serializer: nó chỉ giúp mã nguồn dễ đọc.
- Dùng `\u0020` để cố giữ trailing space: Unicode escape được xử lý sớm, không có tác dụng tương đương `\s`.
- Dùng text block cho một chuỗi ngắn một dòng mà không tăng khả năng đọc: dấu `"..."` thường đơn giản hơn.

## 2. Mã sinh động: Hidden Classes hỗ trợ sinh bytecode khi chạy

### 2.1. Khi nào một lớp cần được sinh động?

Trong thư viện proxy, framework, runtime xử lý lambda hoặc một bộ sinh mã, chương trình có thể phải tạo bytecode để triển khai một hành vi chỉ biết khi chạy. Việc định nghĩa vô số lớp có tên thông thường có thể gây va chạm tên và làm phức tạp quản lý vòng đời. **Hidden Class** là lớp được JVM định nghĩa từ mảng byte theo định dạng `.class`, nhưng không có tên nhị phân bình thường để mã bytecode khác tham chiếu trực tiếp.

API cốt lõi:

- `MethodHandles.lookup()` lấy một `Lookup` gắn với ngữ cảnh quyền truy cập hiện tại.
- `Lookup.defineHiddenClass(byte[], boolean, ClassOption...)` định nghĩa lớp ẩn từ classfile hợp lệ và trả về `Lookup` cho lớp ấy.
- `lookupClass()` lấy đối tượng `Class<?>` của lớp ẩn; `Class.isHidden()` cho biết lớp có ẩn hay không.
- `Class.forName(hidden.getName())` không phải cách tìm lại hidden class. Thành phần tạo ra lớp cần giữ tham chiếu `Class`, `Lookup` hoặc `MethodHandle` cần thiết.

Các điều kiện quan trọng: bytecode phải hợp lệ và thuộc cùng runtime package phù hợp với lớp dùng `Lookup`; `Lookup` phải có quyền truy cập đầy đủ cần thiết. Nếu bytecode đến từ nguồn không tin cậy, không được xem việc dùng hidden class như một cơ chế sandbox hay hàng rào bảo mật.

### 2.2. Ví dụ độc lập: dùng bytecode đã biên dịch để tạo một hidden class

Ví dụ sau cố tình lấy bytecode từ một nested class đã biên dịch để tập trung vào cơ chế `defineHiddenClass`. Trong framework thực, các byte ấy thường được sinh ra trong lúc chạy bằng trình tạo bytecode.

**Tệp `HiddenClassDemo.java`:**

~~~java
import java.io.InputStream;
import java.lang.invoke.MethodHandles;

public class HiddenClassDemo {
    public static class Action implements Runnable {
        public Action() {}

        @Override
        public void run() {
            System.out.println("Action invoked");
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes;
        try (InputStream in = HiddenClassDemo.class
                .getResourceAsStream("HiddenClassDemo$Action.class")) {
            if (in == null) {
                throw new IllegalStateException("Class bytes not found");
            }
            bytes = in.readAllBytes();
        }

        Class<?> hidden = MethodHandles.lookup()
                .defineHiddenClass(bytes, true)
                .lookupClass();

        Runnable action = (Runnable) hidden
                .getDeclaredConstructor()
                .newInstance();

        action.run();
        System.out.println("isHidden=" + hidden.isHidden());
    }
}
~~~

Biên dịch và chạy ở cùng thư mục chứa tệp nguồn:

~~~bash
javac --release 15 HiddenClassDemo.java
java HiddenClassDemo
~~~

Kết quả:

~~~text
Action invoked
isHidden=true
~~~

`javac` tạo cả `HiddenClassDemo.class` và `HiddenClassDemo$Action.class`. `getResourceAsStream` đọc bytecode của `Action`; `defineHiddenClass` tạo thêm một kiểu runtime độc lập, được đánh dấu là ẩn; chương trình dùng đối tượng `Class<?>` nhận được để tạo instance và gọi `Runnable.run()`. Ví dụ là minh họa cơ chế, không phải yêu cầu ứng dụng nghiệp vụ phải tự tạo class ẩn.

### 2.3. Vòng đời, quyền truy cập và các ngộ nhận

- Mặc định một hidden class có thể được dỡ tải khi không còn được tham chiếu, ngay cả khi class loader vẫn sống; **không có bảo đảm sẽ dỡ ngay**. Tùy chọn `ClassOption.STRONG` gắn vòng đời mạnh hơn với class loader.
- `ClassOption.NESTMATE` có thể cho hidden class tham gia cùng nest để truy cập thành viên `private` theo quy tắc nestmate. Chỉ dùng khi framework thật sự cần quyền ấy.
- Hidden class vẫn là kiểu Java thực, có thể triển khai interface và được truy cập qua reflection/Method Handles nếu nắm giữ `Class`; chữ “hidden” chỉ đặc tính định danh/liên kết, **không có nghĩa mã được mã hóa hoặc tuyệt đối bí mật**.
- Không dùng hidden class thay cho `class`/`interface` thông thường trong nghiệp vụ. Phần lớn ứng dụng chỉ cần dùng thư viện; hãy để framework chịu trách nhiệm sinh, cache và giải phóng lớp.
- Nếu sinh quá nhiều class hoặc giữ tham chiếu vào `Class`/`MethodHandle` lâu dài, metadata vẫn có thể tiêu thụ bộ nhớ. Theo dõi metaspace và vòng đời đối tượng, đừng mặc định “hidden” là “không tốn tài nguyên”.

## 3. Chữ ký số EdDSA: ký dữ liệu và phát hiện sửa đổi

### 3.1. Mục đích và thuật toán

**EdDSA** (Edwards-curve Digital Signature Algorithm) là họ thuật toán chữ ký số bất đối xứng; Java 15 bổ sung hỗ trợ **Ed25519** và **Ed448** qua Java Cryptography Architecture (JCA). Hai thành phần dùng thường xuyên:

- `KeyPairGenerator.getInstance("Ed25519")` tạo cặp khóa: khóa `private` để ký và khóa `public` để kiểm chứng.
- `Signature.getInstance("Ed25519")` xử lý `initSign` → `update` → `sign` và `initVerify` → `update` → `verify`.

Đây là **chữ ký**, không phải mã hóa nội dung: ký không che giấu thông điệp; nó cho phép bên xác minh nhận biết dữ liệu có bị sửa hay không và kiểm tra chữ ký có khớp với khóa công khai đã chọn hay không. Muốn xác thực danh tính người ký phải có **cơ chế tin cậy khóa công khai** (chứng chỉ, khóa được phân phối an toàn, danh sách khóa tin cậy...). Không nên nhầm Ed25519 với X25519: X25519 thường dùng cho thỏa thuận khóa, không phải thuật toán `Signature` tương đương.

### 3.2. Ví dụ độc lập: ký dữ liệu gốc, thử xác minh dữ liệu đã sửa

**Tệp `Ed25519Demo.java`:**

~~~java
import java.nio.charset.StandardCharsets;
import java.security.*;

public class Ed25519Demo {
    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator =
                KeyPairGenerator.getInstance("Ed25519");
        KeyPair pair = generator.generateKeyPair();

        byte[] original =
                "du lieu hop le".getBytes(StandardCharsets.UTF_8);

        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(pair.getPrivate());
        signer.update(original);
        byte[] digitalSignature = signer.sign();

        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(pair.getPublic());
        verifier.update(original);
        System.out.println(
                "original=" + verifier.verify(digitalSignature));

        verifier.initVerify(pair.getPublic());
        verifier.update(
                "du lieu da sua".getBytes(StandardCharsets.UTF_8));
        System.out.println(
                "changed=" + verifier.verify(digitalSignature));
    }
}
~~~

~~~bash
javac --release 15 Ed25519Demo.java
java Ed25519Demo
~~~

Kết quả:

~~~text
original=true
changed=false
~~~

Chữ ký được tạo trên byte của thông điệp gốc; khi thay dữ liệu đầu vào, `verify` trả về `false`. Vì khóa được tạo mới mỗi lần chạy, byte của chữ ký sẽ thay đổi giữa các lần chạy, nhưng hai kết quả boolean trên là điều mong đợi với cùng cặp khóa trong một lần chạy.

### 3.3. Áp dụng an toàn trong hệ thống

- Dùng đúng thuật toán giữa ký và xác minh, cùng dữ liệu byte và encoding; thỏa thuận một biểu diễn dữ liệu nhất quán khi ký JSON/file.
- Bảo vệ **private key** bằng kho khóa hoặc dịch vụ quản lý khóa thích hợp. Đừng ghi private key hay tài liệu bí mật vào log và đừng hard-code khóa bí mật vào nguồn.
- Bên nhận phải xác minh **public key thuộc đúng chủ thể đáng tin**. Nếu ai cũng có thể thay public key đi kèm dữ liệu, việc kiểm tra chữ ký mất ý nghĩa xác thực.
- Ký đúng dữ liệu cần bảo vệ, kể cả metadata quan trọng như định danh tài liệu, phiên bản và ngữ cảnh nếu giao thức yêu cầu. Cân nhắc replay attack trong thiết kế giao thức; chữ ký hợp lệ của thông điệp cũ vẫn có thể hợp lệ nếu thiếu nonce/timestamp và quy tắc chống phát lại.
- Kiểm tra provider/JDK hỗ trợ thuật toán trong môi trường triển khai. Không tùy tiện coi chữ ký số thay thế TLS, phân quyền hay mã hóa.

## 4. Bộ thu gom rác: G1, ZGC, Shenandoah và quyết định dựa trên đo lường

### 4.1. Vấn đề GC giải quyết và không giải quyết

Garbage collector tự động nhận diện các đối tượng **không còn reachable** để thu hồi heap. Nó giúp quản lý bộ nhớ đối tượng Java, nhưng không tự động đóng file, socket hoặc kết nối database; dùng `try-with-resources`/`close()` cho tài nguyên có vòng đời. GC không sửa được memory leak do cache/listener/static reference giữ đối tượng sống vô hạn, và không bảo đảm ứng dụng không gặp `OutOfMemoryError`.

Các chỉ số quan trọng khi chọn GC:

- **Pause latency**: thời gian dừng các luồng ứng dụng do hoạt động GC, quan trọng với p95/p99/p99.9 của request.
- **Throughput**: phần công việc ứng dụng hoàn thành trên CPU/thời gian nhất định.
- **Footprint/headroom**: heap sống, tốc độ cấp phát, CPU và RAM dự phòng để GC làm việc đồng thời.
- **Khả năng ổn định dưới tải thật**: kích thước heap, số core, kiểu object allocation, áp lực container và giới hạn bộ nhớ.

Không có GC nào tối ưu mọi chỉ số cùng lúc; “low pause” không đồng nghĩa không bao giờ có stop-the-world.

### 4.2. Các lựa chọn còn thiết thực

| Collector | Điểm chính | Khi nào cân nhắc |
| --- | --- | --- |
| **G1** | GC mặc định trong nhiều cấu hình HotSpot server, cân bằng throughput và mục tiêu pause | Lựa chọn xuất phát cho đa số dịch vụ; đo trước khi đổi |
| **ZGC** | Thu gom phần lớn công việc đồng thời, ưu tiên độ trễ thấp, hỗ trợ heap lớn | Dịch vụ nhạy với p99 latency, có ngân sách CPU/RAM thích hợp |
| **Shenandoah** | Concurrent GC, giảm thời gian pause kể cả khi heap lớn | Workload nhạy với pause khi bản JDK/bản phân phối hỗ trợ và thử nghiệm thực tế tốt |

**Mốc còn hữu ích của Java 15:** ZGC (JEP 377) và Shenandoah (JEP 379) được đưa vào trạng thái dùng cho production. Trong JDK hiện đại, chi tiết triển khai tiếp tục thay đổi: **ZGC từ JDK 24 dùng mô hình generational**, và tùy chọn cũ `ZGenerational` đã bị loại bỏ. Vì vậy, với JDK 24 trở lên, bật ZGC bằng `-XX:+UseZGC`, **không** sao chép hướng dẫn cũ về bật/tắt `ZGenerational`. Shenandoah còn có chế độ generational trên những JDK phù hợp, nhưng cấu hình mặc định và độ sẵn có tùy phiên bản/bản phân phối; cần kiểm tra tài liệu của JDK đang triển khai.

### 4.3. Chạy và quan sát trên JDK hỗ trợ

Giả sử đã biên dịch `Ed25519Demo.java` ở phần trước, có thể dùng những lệnh sau để chạy cùng chương trình với các collector khác nhau. **Chạy từng lệnh riêng** để so sánh, không ghép các tùy chọn collector vào cùng một JVM.

G1:

~~~bash
java -Xms256m -Xmx1g -XX:+UseG1GC -Xlog:gc -cp . Ed25519Demo
~~~

ZGC:

~~~bash
java -Xms256m -Xmx1g -XX:+UseZGC -Xlog:gc -cp . Ed25519Demo
~~~

Shenandoah, khi bản JDK có hỗ trợ:

~~~bash
java -Xms256m -Xmx1g -XX:+UseShenandoahGC -Xlog:gc -cp . Ed25519Demo
~~~

Mỗi lần chạy phần mã Ed25519 vẫn in `original=true` và `changed=false`; các dòng GC log có thể khác nhau theo collector, phiên bản JVM, máy và workload, nên **không có stdout GC cố định** để học thuộc. Chương trình nhỏ thường không đủ tạo ra nhiều chu kỳ GC; muốn đánh giá thật hãy chạy dịch vụ/tải thử có phân bổ đối tượng tương ứng production.

Với chẩn đoán chi tiết hơn, dùng cú pháp unified logging của JVM:

~~~bash
java -Xms256m -Xmx1g -XX:+UseZGC \
  -Xlog:gc*:file=gc.log:time,uptime,level,tags \
  -cp . Ed25519Demo
~~~

Dấu `\` cuối dòng ở khối lệnh trên là cách xuống dòng của shell Unix. Trên Windows PowerShell, nhập thành **một dòng** hoặc dùng cú pháp nối dòng của PowerShell; không copy dấu `\` như lệnh Java. Tệp `gc.log` là đầu ra quan sát, không phải tiêu chí QA về nội dung ứng dụng.

Đọc log để tìm thời điểm/cường độ GC, pause, heap trước và sau collection, allocation pressure. Kết hợp đo p95/p99 latency của request, throughput, CPU, RSS và live set. Có thể dùng Java Flight Recorder (JFR), JDK Mission Control hoặc công cụ quan sát phù hợp; mỗi chỉ số riêng lẻ dễ dẫn đến kết luận sai.

### 4.4. Quy trình chọn và điều chỉnh collector

1. **Bắt đầu bằng cấu hình JVM phù hợp và đo baseline** ở tải đại diện: request rate, latency percentile, CPU/RAM, heap usage, GC pause, số lần collection.
2. **Xác định mục tiêu**: nếu hệ thống chưa vi phạm giới hạn pause, giữ collector hiện tại có thể tốt hơn. Nếu p99 bị GC kéo dài, thử ZGC hoặc Shenandoah trên đúng bản JDK phát hành.
3. **Cấp headroom hợp lý:** cấu hình `-Xmx` theo RAM thực tế và phần bộ nhớ ngoài heap; concurrent GC cần dung lượng/CPU để vừa thu gom vừa phục vụ luồng ứng dụng. `-Xms` và `-Xmx` có vai trò khác nhau, đừng đặt theo công thức cứng cho mọi môi trường.
4. **Chỉ thay một nhóm biến mỗi lần:** cùng workload, cùng độ dài bài test, cùng tài nguyên, rồi so sánh p99, throughput, CPU và footprint. Ghi rõ phiên bản JDK và collector trong kết quả.
5. **Xử lý nguyên nhân gốc:** giảm allocations không cần thiết, giới hạn cache, đóng tài nguyên và xem heap dump khi có leak. Đổi GC không thay thế việc sửa hành vi tạo/giữ đối tượng.

Những sai lầm thường gặp là chọn ZGC chỉ vì nghe “nhanh hơn”, hiểu thời gian pause thấp là throughput luôn cao hơn, chỉ xem số lần GC mà bỏ qua tổng tải, cố ép `System.gc()` để “giải phóng ngay”, hoặc bê các flag cấu hình từ JDK cũ sang JDK mới mà không kiểm tra. Các flags và chế độ của GC có thể thay đổi qua release; luôn kiểm chứng trên runtime đang dùng.

## 5. Liên hệ với dự án Java thực tế

Một ứng dụng dịch vụ có thể dùng đồng thời cả bốn chủ đề nhưng ở bốn lớp trách nhiệm:

1. Tầng xây dựng dữ liệu dùng **Text Blocks** để giữ SQL/JSON mẫu rõ ràng; dữ liệu đầu vào thật vẫn qua API parameterized/serializer.
2. Framework runtime có thể tạo **Hidden Classes** cho lời gọi động hoặc proxy. Đội phát triển hiểu để chẩn đoán class loading/metaspace, thường không tự thao tác bytecode.
3. Dịch vụ phát hành tài liệu dùng **Ed25519** ký một bản ghi byte xác định; bên nhận kiểm tra bằng public key tin cậy trước khi chấp nhận.
4. Dịch vụ hoạt động trên **G1/ZGC/Shenandoah** theo mục tiêu độ trễ và kết quả đo dưới tải; đây là quyết định vận hành JVM, không tác động trực tiếp đến cú pháp chuỗi hay thuật toán chữ ký.

### Tự kiểm tra

**Câu 1.** Text Block có tự làm câu SQL an toàn trước SQL injection không?  
**Đáp án:** Không. Đây chỉ là cú pháp tạo `String`; dùng `PreparedStatement` với tham số cho dữ liệu động.

**Câu 2.** Tạo Hidden Class có làm code an toàn khi chạy bytecode bất kỳ từ Internet không?  
**Đáp án:** Không. Hidden Class là cơ chế định nghĩa/liên kết lớp, không phải sandbox; bytecode và quyền truy cập phải được kiểm soát.

**Câu 3.** `verify(signature) == true` có đủ xác thực danh tính người gửi không?  
**Đáp án:** Chưa đủ nếu public key chưa được liên kết tin cậy với đúng chủ thể hoặc giao thức chưa chống phát lại.

**Câu 4.** ZGC đồng nghĩa ứng dụng không bao giờ bị pause GC?  
**Đáp án:** Không. ZGC giảm pause bằng xử lý đồng thời, song vẫn cần theo dõi latency, CPU và heap headroom.

**Câu 5.** Với JDK 24+, nên bật ZGC bằng flag nào?  
**Đáp án:** `-XX:+UseZGC`; tránh các hướng dẫn cũ dùng `ZGenerational` vì tùy chọn đó đã bị loại bỏ.

## Tài liệu tham khảo chính thức

- [JEP 378 — Text Blocks](https://openjdk.org/jeps/378) và [Programmer's Guide to Text Blocks](https://docs.oracle.com/en/java/javase/15/text-blocks/index.html)
- [JEP 371 — Hidden Classes](https://openjdk.org/jeps/371) và [MethodHandles.Lookup API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html)
- [JEP 339 — Edwards-Curve Digital Signature Algorithm](https://openjdk.org/jeps/339) và [Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/26/docs/specs/security/standard-names.html)
- [JEP 377 — ZGC Production](https://openjdk.org/jeps/377), [JEP 379 — Shenandoah Production](https://openjdk.org/jeps/379)
- [Oracle JDK 24 — The Z Garbage Collector](https://docs.oracle.com/en/java/javase/24/gctuning/z-garbage-collector.html), [JDK 26 — Available Collectors](https://docs.oracle.com/en/java/javase/26/gctuning/available-collectors.html) và [JDK 26 java command options](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
