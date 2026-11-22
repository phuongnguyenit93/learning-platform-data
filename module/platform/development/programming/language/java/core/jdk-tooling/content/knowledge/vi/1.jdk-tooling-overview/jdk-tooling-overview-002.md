# Bài toán công cụ JDK giải quyết

JDK Tooling giải quyết bài toán biến mã nguồn Java thành một chương trình có thể biên dịch, chạy, kiểm tra, đóng gói, phân phối và vận hành. Khi dự án lớn dần, các công cụ này còn giúp nhà phát triển hiểu cấu trúc phụ thuộc, tạo tài liệu, điều tra lỗi và chuẩn bị môi trường chạy phù hợp.

Một tệp `.java` chỉ là văn bản mô tả chương trình. Máy tính không thực thi trực tiếp văn bản Java. Quy trình cần một bộ công cụ để chuyển đổi mã nguồn thành bytecode, một môi trường chạy để thực thi bytecode, và các tiện ích hỗ trợ những công việc xung quanh vòng đời phần mềm.

## 1. Phân biệt JDK, JVM và các công cụ JDK

- **JVM (Java Virtual Machine)** là máy ảo thực thi bytecode Java. JVM chịu trách nhiệm nạp lớp, kiểm tra bytecode, liên kết các lớp, quản lý bộ nhớ và thực thi chương trình.
- **JDK (Java Development Kit)** là bộ công cụ dành cho phát triển Java. JDK có trình biên dịch `javac`, trình chạy `java`, công cụ tạo archive `jar`, công cụ tài liệu `javadoc`, cùng nhiều tiện ích phân tích và chẩn đoán.
- **JDK tools** là các chương trình dòng lệnh đi kèm JDK. Mỗi công cụ xử lý một phần công việc cụ thể trong quy trình phát triển và vận hành.

JDK không thay thế JVM: JVM là thành phần thực thi, còn JDK cung cấp môi trường và công cụ để tạo, kiểm tra, đóng gói và chẩn đoán chương trình Java. Từ Java 9, JDK được tổ chức theo mô hình module và có thể tạo runtime image tùy chỉnh; cách cài đặt và phân phối runtime vì vậy không nên được hiểu đơn giản là luôn có một gói JRE riêng như các phiên bản Java cũ.

## 2. Bài toán thứ nhất: chuyển mã nguồn thành bytecode

**Vấn đề:** Nhà phát triển viết mã Java dễ đọc, nhưng JVM cần bytecode trong các tệp `.class`. Nếu không có bước biên dịch, lỗi cú pháp, kiểu dữ liệu hoặc tham chiếu không hợp lệ có thể chỉ được phát hiện muộn hoặc chương trình không thể chạy.

**Công cụ chính: `javac`**

`javac` đọc mã nguồn `.java`, kiểm tra cú pháp và kiểu dữ liệu, sau đó tạo bytecode trong các tệp `.class`. Trình biên dịch phát hiện nhiều lỗi trước khi chương trình được khởi chạy, giúp vòng phản hồi phát triển nhanh và rõ ràng hơn.

Ví dụ, tạo tệp `src/HelloJdkTooling.java`:

```java
public class HelloJdkTooling {
    public static void main(String[] args) {
        System.out.println("Hello from JDK tooling!");
    }
}
```

Tạo thư mục đầu ra rồi biên dịch:

```bash
mkdir out
javac -d out src/HelloJdkTooling.java
```

Sau khi biên dịch thành công, lớp `HelloJdkTooling` được ghi vào `out/HelloJdkTooling.class`. Chạy chương trình bằng:

```bash
java -cp out HelloJdkTooling
```

Kết quả:

```text
Hello from JDK tooling!
```

Một số tùy chọn `javac` thường dùng:

| Tùy chọn | Ý nghĩa |
|---|---|
| `-d <dir>` | Chỉ định thư mục chứa các tệp `.class` được tạo ra. |
| `-cp` hoặc `-classpath` | Khai báo classpath để trình biên dịch tìm các lớp và thư viện cần thiết. |
| `--release <version>` | Biên dịch theo phiên bản Java mục tiêu, bao gồm tập API được hỗ trợ cho phiên bản đó. |
| `-encoding UTF-8` | Chỉ định encoding của tệp nguồn khi cần kiểm soát rõ cách đọc văn bản. |
| `-parameters` | Giữ tên tham số trong metadata của bytecode để các API reflection có thể truy xuất. |

Ví dụ, nếu ứng dụng cần tương thích với Java 17, có thể dùng `javac --release 17` khi biên dịch bằng một JDK hỗ trợ tùy chọn này. Điều đó giúp tránh vô tình phụ thuộc vào API mới hơn phiên bản đích. Nó không tự động kiểm tra mọi khác biệt môi trường hoặc thư viện bên ngoài; các dependency cũng cần có phiên bản tương thích.

**Giá trị:** `javac` tạo ra đầu ra mà JVM hiểu được và phát hiện nhiều lỗi sớm, trước khi triển khai.

## 3. Bài toán thứ hai: khởi chạy đúng lớp và đúng dependency

**Vấn đề:** Có bytecode chưa đủ để chạy ứng dụng. JVM cần biết lớp nào chứa điểm vào `main`, các lớp phụ thuộc nằm ở đâu, và ứng dụng cần tham số hoặc cấu hình nào. Khi thiếu hoặc đặt sai classpath/module path, chương trình có thể gặp lỗi như `ClassNotFoundException`, `NoClassDefFoundError` hoặc không tìm thấy lớp chính.

**Công cụ chính: `java`**

Lệnh `java` khởi chạy JVM, nạp lớp chính và gọi phương thức `public static void main(String[] args)` nếu ứng dụng dùng kiểu entry point truyền thống.

Các dạng gọi thường gặp:

```bash
# Chạy một lớp từ thư mục chứa bytecode
java -cp out HelloJdkTooling

# Truyền đối số cho chương trình
java -cp out HelloJdkTooling input.txt --verbose

# Truyền system property cho ứng dụng
java -Dapp.env=dev -cp out HelloJdkTooling
```

Classpath là danh sách vị trí để tìm lớp và tài nguyên. Dấu phân cách giữa các phần tử phụ thuộc hệ điều hành: Windows thường dùng dấu chấm phẩy (`;`), còn Linux và macOS thường dùng dấu hai chấm (`:`). Vì vậy, script chạy ứng dụng nên tính đến hệ điều hành hoặc dùng cơ chế build/run quản lý classpath thay vì giả định một dấu phân cách duy nhất.

Với ứng dụng được đóng gói thành JAR có khai báo lớp chính trong manifest, có thể chạy:

```bash
java -jar app.jar
```

Khi dùng `-jar`, JVM lấy lớp chính từ manifest của JAR. Không nên kỳ vọng các mục classpath truyền riêng bằng `-cp` sẽ bổ sung dependency cho chế độ này; dependency cần được khai báo phù hợp trong manifest hoặc được cung cấp qua cách đóng gói/chạy khác.

**Giá trị:** trình chạy chuẩn hóa cách khởi động ứng dụng và cung cấp các tùy chọn cấu hình JVM, classpath, module path, system property và tham số chương trình.

## 4. Bài toán thứ ba: gom các lớp thành đơn vị có thể lưu trữ và phân phối

**Vấn đề:** Một ứng dụng thường có nhiều tệp `.class`, tài nguyên và metadata. Phân phối từng tệp rời rạc dễ thiếu tệp, sai cấu trúc thư mục hoặc khó xác định lớp khởi chạy.

**Công cụ chính: `jar`**

`jar` tạo và thao tác với Java Archive (JAR), một định dạng archive dựa trên ZIP. JAR có thể chứa bytecode, tài nguyên và manifest. Manifest có thể khai báo lớp chính để hỗ trợ chạy bằng `java -jar`.

Với ví dụ ở phần trước, tạo JAR:

```bash
jar --create --file app.jar --main-class HelloJdkTooling -C out .
```

Chạy JAR:

```bash
java -jar app.jar
```

Kết quả:

```text
Hello from JDK tooling!
```

Một số lệnh hữu ích:

```bash
# Liệt kê nội dung archive
jar --list --file app.jar

# Giải nén archive vào thư mục hiện tại
jar --extract --file app.jar

# Xem trợ giúp và các tùy chọn của jar
jar --help
```

JAR giúp đóng gói các lớp và tài nguyên của ứng dụng thành một tệp dễ lưu trữ, vận chuyển và triển khai. Tuy nhiên, một JAR thông thường **không tự động chứa mọi thư viện bên ngoài**. Nếu ứng dụng phụ thuộc vào các JAR khác, cần cung cấp chúng trên classpath/module path, khai báo cách tìm dependency trong manifest, hoặc dùng quy trình build/đóng gói tạo artifact phù hợp. Không nên nhầm JAR thông thường với fat JAR/uber JAR do plugin build tạo ra.

**Giá trị:** `jar` giảm sự phức tạp khi quản lý nhiều tệp đầu ra và tạo một artifact Java có cấu trúc rõ ràng.

## 5. Bài toán thứ tư: tạo tài liệu API có thể tra cứu

**Vấn đề:** Khi nhiều người cùng sử dụng một thư viện hoặc một module, chỉ đọc mã nguồn là chưa đủ. Người dùng cần biết lớp và phương thức làm gì, tham số có ý nghĩa gì, giá trị trả về ra sao và ngoại lệ nào có thể xảy ra.

**Công cụ chính: `javadoc`**

`javadoc` đọc khai báo Java cùng các comment theo định dạng Javadoc để tạo tài liệu HTML. Các thẻ như `@param`, `@return`, `@throws` giúp mô tả hợp đồng của API.

Ví dụ, tạo tệp `src/Calculator.java`:

```java
public class Calculator {
    /**
     * Tính tổng hai số nguyên.
     *
     * @param a số hạng thứ nhất
     * @param b số hạng thứ hai
     * @return tổng của a và b
     */
    public static int add(int a, int b) {
        return a + b;
    }
}
```

Có thể tạo tài liệu cho tệp nguồn bằng:

```bash
javadoc -d docs src/Calculator.java
```

Thư mục `docs` sẽ chứa các trang HTML được sinh ra. Tài liệu có chất lượng phụ thuộc vào comment và cấu trúc API mà nhóm phát triển cung cấp; `javadoc` không thể tự suy ra đầy đủ ý định nghiệp vụ từ tên phương thức.

**Giá trị:** `javadoc` biến thông tin nằm trong mã nguồn thành tài liệu API thống nhất, có thể xuất bản và tra cứu.

## 6. Bài toán thứ năm: thử nghiệm nhanh mà không cần tạo dự án hoàn chỉnh

**Vấn đề:** Đôi khi nhà phát triển chỉ muốn thử một biểu thức, kiểm tra cách dùng API hoặc xác nhận một đoạn mã nhỏ. Tạo dự án, tệp nguồn, biên dịch và chạy cho mỗi thử nghiệm sẽ làm chậm quá trình khám phá.

**Công cụ chính: `jshell`**

`jshell` là môi trường tương tác REPL (Read-Eval-Print Loop), cho phép nhập biểu thức và câu lệnh Java rồi xem kết quả ngay.

```text
$ jshell
|  Welcome to JShell -- Version 17
jshell> int total = 10 + 20;
total ==> 30

jshell> System.out.println(total);
30

jshell> /exit
```

`jshell` phù hợp để học ngôn ngữ, thử API, kiểm tra phép tính và khám phá hành vi của một đoạn mã nhỏ. Nó không thay thế cấu trúc, kiểm thử tự động, quản lý dependency hay quy trình build của ứng dụng thực tế.

**Giá trị:** giảm thời gian giữa câu hỏi và kết quả thử nghiệm, đặc biệt trong học tập và khám phá API.

## 7. Bài toán thứ sáu: hiểu bytecode và phân tích dependency

**Vấn đề:** Khi ứng dụng chạy khác kỳ vọng, nhà phát triển có thể cần biết bytecode thực tế chứa gì hoặc thư viện nào phụ thuộc vào package/module nào. Chỉ nhìn mã nguồn đôi khi chưa đủ, nhất là khi làm việc với thư viện đã biên dịch hoặc ứng dụng cũ.

**Các công cụ chính: `javap` và `jdeps`**

- `javap` là disassembler cho tệp lớp Java. Nó có thể hiển thị khai báo lớp, chữ ký phương thức, modifier và bytecode.
- `jdeps` phân tích dependency ở mức lớp/package/module, giúp nhận diện các phụ thuộc và hỗ trợ chuẩn bị cho việc chuyển đổi sang module hoặc loại bỏ dependency không cần thiết.

Ví dụ:

```bash
# Hiển thị chữ ký và thành phần của lớp đã biên dịch
javap -classpath out HelloJdkTooling

# Hiển thị bytecode của phương thức
javap -c -classpath out HelloJdkTooling

# Phân tích dependency của một JAR
jdeps --summary app.jar
```

Các công cụ này hỗ trợ điều tra và phân tích tĩnh. Kết quả của `jdeps` không thay thế kiểm thử lúc chạy: một số dependency được nạp động qua reflection, service loader hoặc cấu hình có thể không được suy ra đầy đủ chỉ từ bytecode.

**Giá trị:** giúp nhìn thấy cấu trúc đã biên dịch và mối quan hệ phụ thuộc, từ đó hỗ trợ debug, nâng cấp và modular hóa.

## 8. Bài toán thứ bảy: tạo runtime nhỏ gọn và bộ cài cho ứng dụng

**Vấn đề:** Một ứng dụng Java có thể chỉ dùng một phần nhỏ trong các module của nền tảng Java. Khi triển khai, mang theo một runtime lớn hơn nhu cầu có thể làm tăng dung lượng phân phối. Người dùng cuối cũng có thể không có sẵn Java hoặc không biết cách cài đặt và cấu hình runtime.

**Các công cụ chính: `jlink` và `jpackage`**

- `jlink` liên kết các module cần thiết để tạo một runtime image tùy chỉnh. Công cụ này làm việc với module và yêu cầu các module phụ thuộc được xác định phù hợp.
- `jpackage` đóng gói ứng dụng thành định dạng phân phối phù hợp với nền tảng, chẳng hạn gói cài đặt cho Windows, macOS hoặc Linux. Định dạng và yêu cầu tạo gói phụ thuộc hệ điều hành; thường cần build trên nền tảng đích và có thể cần công cụ đóng gói hệ thống.

Một runtime image tùy chỉnh có thể được tạo bằng `jlink` khi đã biết module gốc của ứng dụng, ví dụ:

```bash
jlink --add-modules java.base --output runtime
```

Lệnh trên chỉ tạo runtime chứa module `java.base`, phù hợp minh họa cách hoạt động của `jlink`; ứng dụng thực tế phải thêm đầy đủ các module mà nó sử dụng. Có thể dùng `jdeps` và kiểm thử để hỗ trợ xác định tập module cần thiết.

**Giá trị:** `jlink` giúp kiểm soát thành phần runtime được phân phối; `jpackage` giúp đưa ứng dụng đến người dùng dưới dạng gói cài đặt quen thuộc hơn.

## 9. Bài toán thứ tám: chẩn đoán ứng dụng đang chạy

**Vấn đề:** Một ứng dụng có thể biên dịch thành công nhưng gặp sự cố khi vận hành: treo, phản hồi chậm, tiêu thụ CPU cao, dùng quá nhiều bộ nhớ hoặc có nhiều luồng bị chặn. Việc chỉ xem log ứng dụng có thể không đủ để tìm nguyên nhân.

**Một số công cụ chẩn đoán trong JDK:**

| Công cụ | Công dụng chính |
|---|---|
| `jcmd` | Gửi lệnh chẩn đoán tới JVM đang chạy; có thể liệt kê lệnh được JVM hỗ trợ và yêu cầu tạo dữ liệu chẩn đoán. |
| `jstack` | Lấy thread dump để xem trạng thái các luồng và stack trace tại thời điểm chụp. |
| `jmap` | Hỗ trợ lấy thông tin heap và tạo heap dump trong các tình huống phù hợp. |
| `jstat` | Hiển thị một số thống kê về hoạt động JVM, garbage collection và vùng bộ nhớ. |
| `jfr` | Làm việc với bản ghi Java Flight Recorder để thu thập và phân tích sự kiện phục vụ điều tra hiệu năng. |
| `jconsole` | Công cụ giao diện đồ họa để quan sát một số chỉ số và quản lý kết nối JMX. |

Ví dụ, liệt kê các tiến trình Java mà `jcmd` có thể truy cập và xem lệnh hỗ trợ:

```bash
jcmd
jcmd <pid> help
```

Lấy thread dump bằng:

```bash
jcmd <pid> Thread.print
```

Trong đó `<pid>` là mã tiến trình của ứng dụng Java cần kiểm tra. Quyền truy cập tiến trình, người dùng hệ điều hành, cấu hình JVM và môi trường chạy có thể ảnh hưởng đến việc một lệnh chẩn đoán có thực hiện được hay không.

Thread dump giúp tìm luồng bị block, deadlock hoặc chờ tài nguyên. Heap dump hữu ích khi điều tra nghi vấn rò rỉ bộ nhớ nhưng có thể rất lớn và chứa dữ liệu nhạy cảm của ứng dụng. JFR có thể ghi nhận sự kiện về CPU, allocation, GC, thread và nhiều hoạt động JVM khác; cần chọn thời lượng và cấu hình ghi phù hợp với mục tiêu điều tra.

**Giá trị:** các công cụ chẩn đoán cung cấp bằng chứng ở cấp JVM để điều tra vấn đề hiệu năng và độ ổn định trong môi trường thực tế.

## 10. Bài toán thứ chín: quản lý khóa, chứng thư và chữ ký JAR

**Vấn đề:** Ứng dụng có thể cần lưu khóa và chứng thư, thiết lập truststore cho kết nối TLS hoặc ký artifact để người nhận kiểm tra tính toàn vẹn và nguồn phát hành.

**Các công cụ chính: `keytool` và `jarsigner`**

- `keytool` quản lý keystore và certificate: tạo cặp khóa, tạo yêu cầu ký chứng thư, nhập chứng thư và xem thông tin chứng thư.
- `jarsigner` ký JAR và kiểm tra chữ ký của JAR.

Ví dụ xem thông tin một keystore:

```bash
keytool -list -keystore my-keystore.p12
```

Ví dụ kiểm tra chữ ký của một JAR:

```bash
jarsigner -verify -verbose -certs app-signed.jar
```

Ký số giúp phát hiện thay đổi nội dung đã ký và hỗ trợ xác minh danh tính chứng thư theo chuỗi tin cậy. Chữ ký JAR **không mã hóa** nội dung archive và không tự bảo đảm ứng dụng an toàn. Cần bảo vệ private key, kiểm tra nguồn chứng thư và quản lý thời hạn/thu hồi chứng thư theo chính sách của tổ chức. Tránh đưa mật khẩu keystore trực tiếp vào lịch sử shell hoặc script được chia sẻ.

**Giá trị:** hỗ trợ quản lý thông tin tin cậy và bảo vệ tính toàn vẹn của artifact trong quy trình phân phối.

## 11. Ghép các công cụ thành quy trình phát triển

Các công cụ JDK giải quyết những phần khác nhau của cùng một vòng đời:

1. **Viết mã nguồn:** tạo các tệp `.java` và tài nguyên.
2. **Biên dịch:** dùng `javac` để kiểm tra mã nguồn và tạo bytecode.
3. **Chạy thử:** dùng `java` để khởi động ứng dụng với classpath/module path và cấu hình cần thiết.
4. **Thử nghiệm nhanh:** dùng `jshell` để khám phá biểu thức hoặc API nhỏ.
5. **Kiểm tra đầu ra:** dùng `javap` để xem lớp đã biên dịch, `jdeps` để phân tích dependency.
6. **Tạo tài liệu:** dùng `javadoc` để sinh tài liệu API.
7. **Đóng gói:** dùng `jar` để tạo archive chứa lớp và tài nguyên.
8. **Chuẩn bị phân phối:** cân nhắc `jlink` để tạo runtime image và `jpackage` để tạo gói cài đặt.
9. **Bảo vệ artifact:** dùng `keytool` và `jarsigner` khi quy trình yêu cầu quản lý chứng thư và ký số.
10. **Vận hành và điều tra:** dùng `jcmd`, `jstack`, `jmap`, `jstat`, `jfr` hoặc `jconsole` khi cần dữ liệu chẩn đoán.

Không phải dự án nào cũng cần mọi công cụ. Một chương trình học Java có thể chỉ cần `javac` và `java`; một thư viện công khai thường quan tâm thêm `javadoc`; một ứng dụng desktop phân phối cho người dùng cuối có thể cần `jpackage`; một dịch vụ đang chạy có thể cần JFR hoặc thread dump để điều tra sự cố.

## 12. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Có `java` là chắc chắn có thể biên dịch Java. | `java` là trình chạy; cần `javac` để biên dịch. Hãy kiểm tra cả hai lệnh và phiên bản đang được gọi. |
| `javac` báo thành công nghĩa là ứng dụng chắc chắn chạy đúng. | Biên dịch chỉ xác nhận một số điều kiện ở thời điểm compile. Lỗi cấu hình, dependency, dữ liệu và logic vẫn có thể xuất hiện lúc chạy. |
| Một JAR luôn chứa tất cả dependency. | JAR thông thường chứa những gì được đóng gói vào nó. Thư viện ngoài cần được cung cấp hoặc đóng gói theo một quy trình riêng. |
| `-cp` và `--module-path` là một. | Classpath phục vụ cơ chế tìm lớp truyền thống; module path phục vụ hệ module Java. Chọn theo cách tổ chức ứng dụng và thư viện. |
| `jlink` tạo bộ cài đặt hoàn chỉnh. | `jlink` tạo runtime image tùy chỉnh. `jpackage` mới là công cụ đóng gói ứng dụng thành định dạng phân phối phù hợp nền tảng. |
| Ký JAR đồng nghĩa với mã hóa JAR. | Chữ ký số hỗ trợ xác minh tính toàn vẹn và chứng thư; nội dung JAR vẫn có thể được đọc. |
| Công cụ chẩn đoán luôn có thể truy cập mọi tiến trình. | Quyền hệ điều hành, user chạy tiến trình, cấu hình JVM và môi trường có thể giới hạn thao tác. |

Khi một lệnh không được nhận diện hoặc gọi sai phiên bản, kiểm tra đường dẫn và phiên bản của công cụ:

```bash
java --version
javac --version
jar --version
```

Trên Windows có thể dùng `where java` và `where javac`; trên Linux/macOS có thể dùng `which java` và `which javac` để xem executable được tìm thấy qua `PATH`. Nếu `java` và `javac` đến từ hai bản cài đặt khác nhau, kết quả build và chạy có thể không nhất quán. Thiết lập `JAVA_HOME` và `PATH` rõ ràng giúp giảm loại lỗi này.

## 13. Khi nào nên dùng công cụ nào?

| Nhu cầu | Công cụ nên xem xét |
|---|---|
| Biên dịch mã nguồn và kiểm tra lỗi compile | `javac` |
| Chạy lớp hoặc ứng dụng Java | `java` |
| Đóng gói lớp và tài nguyên thành archive | `jar` |
| Tạo tài liệu API HTML | `javadoc` |
| Thử nhanh cú pháp hoặc API | `jshell` |
| Xem chữ ký lớp và bytecode | `javap` |
| Phân tích dependency và module | `jdeps` |
| Tạo runtime image tối giản theo module | `jlink` |
| Tạo gói cài đặt cho người dùng | `jpackage` |
| Quản lý keystore và chứng thư | `keytool` |
| Ký hoặc xác minh chữ ký JAR | `jarsigner` |
| Điều tra luồng, heap và hiệu năng JVM | `jcmd`, `jstack`, `jmap`, `jstat`, `jfr`, `jconsole` |

Các công cụ JDK cung cấp nền tảng thao tác trực tiếp với Java mà không phụ thuộc vào một IDE cụ thể. IDE, Maven và Gradle có thể gọi hoặc tích hợp nhiều công cụ này để tự động hóa quy trình lớn hơn; chúng bổ sung quản lý dự án, dependency và build, còn các lệnh JDK vẫn hữu ích để hiểu chính xác điều gì đang xảy ra bên dưới.

Khi nắm được bài toán mà từng công cụ giải quyết, nhà phát triển có thể chọn đúng công cụ theo từng giai đoạn: biên dịch khi cần tạo bytecode, chạy khi cần khởi động ứng dụng, đóng gói khi cần phân phối, và chẩn đoán khi cần tìm nguyên nhân của sự cố trong JVM.
