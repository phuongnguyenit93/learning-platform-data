# Phân biệt tính năng Java SE với chi tiết triển khai HotSpot

*Ngữ cảnh: định hướng Java 10; các nguyên tắc, API và công cụ dưới đây vẫn có giá trị khi làm việc với JDK hiện đại.*

## 1. Vì sao phải phân biệt?

Một bản phát hành JDK có thể bổ sung cú pháp Java, API chuẩn, công cụ phát triển và tối ưu hóa bên trong JVM. Cùng xuất hiện trong thông báo “JDK 10 có gì mới” **không có nghĩa tất cả đều là tính năng của đặc tả Java SE**.

- **Java SE** quy định hợp đồng mà chương trình và nền tảng Java tuân thủ: ngôn ngữ Java (JLS), máy ảo Java (JVMS) và API thuộc nền tảng Java SE.
- **JDK** là bộ công cụ và môi trường dùng để phát triển, biên dịch, chạy, đóng gói, chẩn đoán ứng dụng Java. JDK chứa một bản triển khai nền tảng và có thể cung cấp công cụ/tính năng ngoài hợp đồng Java SE.
- **HotSpot** là một bản triển khai JVM được sử dụng trong nhiều bản phân phối JDK dựa trên OpenJDK. Nó quyết định nhiều cơ chế chạy thực tế như JIT, garbage collector (GC), quản lý bộ nhớ và chẩn đoán.
- **OpenJDK** là dự án/mã nguồn của một bản triển khai JDK, bao gồm nhiều thành phần (thư viện, công cụ, HotSpot). “OpenJDK” không phải tên khác của đặc tả Java SE hay của riêng HotSpot.

Hệ quả: mã nguồn tuân thủ Java SE và sử dụng API chuẩn thường có thể chuyển giữa các JVM tương thích **cùng phiên bản nền tảng yêu cầu**; thiết lập hoặc giả định về nội bộ HotSpot phải được kiểm tra riêng cho từng JVM, bản dựng và phiên bản.

## 2. Bốn tầng cần nhận diện

| Tầng | Ai quy định/hỗ trợ? | Ví dụ có liên quan Java 10 | Điều được bảo đảm |
| --- | --- | --- | --- |
| **Ngôn ngữ Java** | Java Language Specification (JLS) | `var` cho biến cục bộ có giá trị khởi tạo, được đưa vào Java SE 10 | Quy tắc cú pháp, kiểm tra kiểu và ngữ nghĩa chương trình |
| **Máy ảo theo đặc tả** | Java Virtual Machine Specification (JVMS) | Định dạng class file, bytecode, xác minh và thực thi mã | Ngữ nghĩa JVM phải tuân thủ; không chỉ định thuật toán GC hay JIT cụ thể |
| **Thư viện Java SE** | Java SE API Specification | `List.copyOf(Collection)` từ Java SE 10 | Chữ ký API, hợp đồng hành vi, ngoại lệ và điều kiện được tài liệu hóa |
| **Triển khai/công cụ** | HotSpot, nhà cung cấp JDK hoặc tài liệu công cụ JDK | G1 parallel full GC, AppCDS, tùy chọn `-XX`, `jcmd` | Chỉ những gì bản triển khai và tài liệu phiên bản tương ứng cam kết |

**Lưu ý về độ chính xác:** một API chuẩn có thể cho phép nhiều cách triển khai. Ví dụ, `List.copyOf` trả về danh sách không thể sửa, nhưng tên lớp triển khai cụ thể, cách bố trí đối tượng và chi phí cấp phát không phải lời hứa có thể suy ra từ chữ ký API.

## 3. Các ví dụ thực tế bắt nguồn từ Java 10

### 3.1. `var` là thay đổi ngôn ngữ Java SE, không phải tối ưu hóa HotSpot

JEP 286 mở rộng suy luận kiểu cho **khai báo biến cục bộ có giá trị khởi tạo**. Trình biên dịch xác định kiểu tĩnh từ biểu thức bên phải; `var` không tạo biến có kiểu động. Ví dụ `var number = 10;` có kiểu `int`; một phép gán `number = "text";` sau đó là lỗi biên dịch. `var` không dùng để thay kiểu khai báo trường dữ liệu, kiểu trả về phương thức hoặc tham số phương thức thông thường.

HotSpot không cần có một “kiểu `var`” riêng lúc chạy. Trình biên dịch xử lý phép suy luận kiểu trước khi JVM thực thi class file. Một trình biên dịch phù hợp đặc tả khác cũng có thể hỗ trợ cú pháp này mà không cần là `javac` hay HotSpot.

### 3.2. `List.copyOf` là API Java SE; lớp hiện thực là chi tiết triển khai

Từ Java SE 10, `List.copyOf(collection)` tạo một danh sách không thể sửa phản ánh các phần tử của collection tại thời điểm gọi. Sửa collection nguồn sau đó không làm thay đổi danh sách trả về. Lời gọi từ chối collection nguồn `null` hoặc phần tử `null` theo hợp đồng API. Tuy nhiên, không nên giả định tên lớp cụ thể, identity hay cấu trúc lưu trữ bên trong của danh sách trả về.

Ví dụ Java 17+ sau đây cũng chỉ sử dụng cú pháp/API đã có từ Java 10:

~~~java
// File: BoundaryDemo.java
import java.util.ArrayList;
import java.util.List;

public class BoundaryDemo {
    public static void main(String[] args) {
        var original = new ArrayList<>(List.of("Java", "SE"));
        List<String> snapshot = List.copyOf(original);

        original.add("HotSpot");

        System.out.println("snapshot = " + snapshot);
        System.out.println("original = " + original);
    }
}
~~~

Biên dịch và chạy từ thư mục chứa tệp:

~~~bash
javac BoundaryDemo.java
java BoundaryDemo
~~~

Kết quả từ chương trình (không bật thêm log JVM):

~~~text
snapshot = [Java, SE]
original = [Java, SE, HotSpot]
~~~

Trong ví dụ này:

1. `var` được kiểm tra theo **JLS**; kiểu suy ra của `original` là `ArrayList<String>`, không thay đổi trong quá trình chạy.
2. `List.copyOf` và các phương thức `List`/`ArrayList` được gọi theo **API Java SE**.
3. JVM có thể diễn dịch bytecode hoặc biên dịch JIT, chọn cách cấp phát và thu gom bộ nhớ khác nhau. Những quyết định **triển khai** đó không làm thay đổi kết quả phải tuân thủ của chương trình.
4. `javac`/`java` là công cụ trong JDK. Chúng tạo/chạy chương trình, nhưng việc chúng là công cụ JDK không biến mọi tùy chọn của chúng thành một phần ngôn ngữ Java.

### 3.3. G1 parallel full GC (JEP 307) là cải tiến HotSpot

JDK 10 mang tới cơ chế thực hiện **pha full GC của G1 bằng nhiều luồng** nhằm giảm độ trễ trong tình huống G1 phải thực hiện full GC. Đây là sự thay đổi trong trình thu gom rác của HotSpot; nó **không** phải cú pháp mới, API mới hay quy tắc JVMS bắt buộc mọi JVM phải cài đặt.

Không nhầm “full GC của G1 được song song hóa” với “mọi pha GC đều song song”, “mọi chương trình Java đều tăng tốc” hay “G1 là nghĩa vụ của đặc tả”. Hiệu quả thực tế phụ thuộc workload, heap, phần cứng và phiên bản JVM; cần đo đạc thay vì khẳng định một mức tăng tốc cố định.

Ví dụ tùy chọn `-XX:+UseG1GC` là cách yêu cầu G1 trên **bản HotSpot hỗ trợ tùy chọn này**. Một JVM khác có thể có các GC và tùy chọn khác, dù vẫn chạy cùng mã Java SE.

### 3.4. AppCDS (JEP 310) là cơ chế chia sẻ dữ liệu lớp khi chạy

JDK 10 mở rộng Class-Data Sharing tới các lớp ứng dụng (AppCDS) để hỗ trợ giảm thời gian khởi động và/hoặc dấu chân bộ nhớ trong những tình huống phù hợp. Đây là cơ chế thuộc môi trường chạy/HotSpot; chương trình sử dụng API Java SE không cần dựa vào sự tồn tại của một archive CDS cụ thể.

CDS/AppCDS vẫn là chủ đề tối ưu hóa có ích trong các JDK hiện đại, nhưng cách tạo archive, mặc định và tham số hỗ trợ đã thay đổi qua các bản phát hành. Khi dùng thực tế, kiểm tra tài liệu **đúng JDK đang triển khai** và đo trước–sau; không sao chép nguyên các lệnh thử nghiệm của JDK 10 vào hệ thống hiện tại.

### 3.5. Thread-Local Handshakes và GC interface là cấu trúc bên trong VM

- **JEP 312 – Thread-Local Handshakes:** cho phép HotSpot phối hợp một số thao tác với từng luồng riêng lẻ thay vì lúc nào cũng cần điểm dừng toàn cục. Đây là cơ chế nội bộ; chương trình Java không được giả định một giao thức handshake cụ thể.
- **JEP 304 – Garbage Collector Interface:** cải thiện ranh giới giữa các thành phần GC và phần còn lại của HotSpot để dễ bảo trì/phát triển. Đây là thay đổi kiến trúc mã VM, không phải API Java SE cho ứng dụng chọn hoặc viết GC.

Những cải tiến triển khai có thể mang lại kết quả tích cực trong ứng dụng, nhưng **sự hiện diện của JEP trong cùng phiên bản JDK không xác nhận nó là quy tắc nền tảng Java SE**.

## 4. Quy tắc phân loại một tuyên bố

Hãy tìm **hợp đồng** mà tuyên bố dựa vào:

1. **Cú pháp hoặc quy tắc kiểu?** Tra JLS của phiên bản Java SE tương ứng. Ví dụ: `var` trong khai báo cục bộ → ngôn ngữ Java SE.
2. **Bytecode, class file, kiểm tra kiểu khi liên kết, ngữ nghĩa máy ảo?** Tra JVMS. Đặc tả JVM quy định kết quả và các ràng buộc; không buộc HotSpot, OpenJ9 hay JVM tương thích khác dùng cùng một JIT/GC.
3. **Phương thức, lớp hay module dùng trong mã?** Tra Java SE API Specification, mục `Since`, điều kiện và ngoại lệ. Ví dụ: `List.copyOf` → API Java SE; lớp nội bộ nhận được từ `getClass().getName()` → không phải hợp đồng về tên lớp triển khai.
4. **Tùy chọn khởi chạy, số luồng GC, bố trí heap, vùng nhớ, log hiệu năng?** Tra hướng dẫn VM/JDK của nhà cung cấp và phiên bản. Các flag `-XX` và tên GC là dấu hiệu thường gặp của lớp triển khai HotSpot.
5. **Công cụ `javac`, `java`, `jlink`, `jcmd`?** Tra JDK Tool Specifications và hướng dẫn công cụ. Phân biệt công cụ có sẵn trong JDK với tính năng ngôn ngữ hoặc API của Java SE.
6. **Tài liệu là JEP?** Xem mục tiêu và `Scope` của chính JEP. JEP có thể đề xuất thay đổi ngôn ngữ/API, công cụ, dự án hoặc **implementation**. Chỉ nhãn “JEP” hay “có trong Java 10” không đủ để suy ra mức cam kết tương thích.

| Tuyên bố cần phân loại | Kết luận | Lý do |
| --- | --- | --- |
| “Dùng `var` để suy luận kiểu biến cục bộ” | Java SE — ngôn ngữ | Quy tắc trong JLS, được đưa vào Java 10 |
| “`List.copyOf` tạo danh sách không thể sửa” | Java SE — API | Hợp đồng phương thức công khai từ Java 10 |
| “Danh sách trả về có tên lớp nội bộ X” | Chi tiết triển khai | API không bảo đảm tên/loại lớp hiện thực cụ thể |
| “G1 có full GC song song sau JEP 307” | HotSpot — GC | Cải tiến thuật toán/hiệu năng VM |
| “AppCDS cải thiện khởi động trong workload này” | HotSpot/JDK — tối ưu hóa | Khả năng phụ thuộc triển khai, cấu hình và phép đo |
| “Mọi JVM đều phải nhận `-XX:+UseG1GC`” | **Sai** | Tùy chọn này không phải hợp đồng JVMS |
| “JVM phải thực hiện bytecode theo ngữ nghĩa JVMS” | Java SE — JVM specification | Bắt buộc đối với một JVM tuyên bố tương thích |
| “Tất cả JVM đều biên dịch mọi phương thức bằng JIT” | **Sai** | JIT là chiến lược triển khai, không phải nghĩa vụ của JVMS |

## 5. Kiểm tra môi trường Java đang chạy

Đừng đồng nhất phiên bản đặc tả với tên JVM. Có thể kiểm tra bằng các system property công khai (không cần API nội bộ):

~~~java
// File: RuntimeIdentity.java
public class RuntimeIdentity {
    public static void main(String[] args) {
        System.out.println("Java SE spec: "
                + System.getProperty("java.specification.version"));
        System.out.println("JVM spec: "
                + System.getProperty("java.vm.specification.version"));
        System.out.println("JVM implementation: "
                + System.getProperty("java.vm.name"));
        System.out.println("VM vendor: "
                + System.getProperty("java.vm.vendor"));
    }
}
~~~

~~~bash
javac RuntimeIdentity.java
java RuntimeIdentity
java -version
~~~

**Không có một stdout cố định** cho ví dụ này: phiên bản đặc tả, tên và nhà cung cấp VM thay đổi theo JDK/JVM đang chạy. Các khóa `java.specification.version` và `java.vm.specification.version` nêu phiên bản đặc tả; `java.vm.name`/`java.vm.vendor` mô tả bản triển khai. Lệnh `java -version` giúp đối chiếu bản JDK thực tế, nhưng chuỗi hiển thị không phải tên lớp hoặc tên GC được Java SE bảo đảm.

Khi muốn điều tra GC trên HotSpot, có thể dùng công cụ và logging được bản JDK hiện tại hỗ trợ, chẳng hạn `-Xlog:gc` và `-XX:+UseG1GC`. Đây là **cấu hình và công cụ chẩn đoán của môi trường chạy**. Đừng đưa các option này vào điều kiện đúng/sai của unit test nghiệp vụ và đừng coi log của HotSpot là định dạng chung cho mọi JVM.

## 6. Khả năng chuyển JVM, nâng cấp JDK và kiểm thử

- **Hợp đồng chức năng:** viết unit/integration test cho hành vi được JLS, JVMS và Java SE API quy định. Ví dụ: `List.copyOf` vẫn không thể sửa; trạng thái collection nguồn không thay đổi snapshot.
- **Tương thích phiên bản:** khi dùng `var`/`List.copyOf`, yêu cầu môi trường biên dịch có hỗ trợ Java 10 trở lên và runtime có API tương ứng. Cần xác định phiên bản Java đích của bản phát hành; chỉ đổi runtime mà không kiểm tra bytecode/API có thể gây lỗi.
- **Tách mã ứng dụng khỏi cấu hình JVM:** code Java SE nên tránh import lớp nội bộ `sun.*`, `jdk.internal.*` hoặc phụ thuộc vào tên lớp hiện thực cụ thể. Tùy chọn `-XX` nên nằm trong cấu hình triển khai dành cho JVM hỗ trợ.
- **Kiểm thử hiệu năng riêng:** throughput, độ trễ GC, thời gian khởi động và footprint phải được đo trên workload thật, với cùng điều kiện đo và JVM được ghi rõ. Cải tiến của HotSpot có thể thay đổi qua bản dựng mà không đổi ngữ nghĩa Java SE.
- **Không suy diễn từ một máy:** chạy được với HotSpot của một nhà cung cấp không chứng minh mọi lựa chọn flag, log hoặc tối ưu hóa sẽ hoạt động giống hệt trên JVM khác.
- **Đọc đúng tài liệu phiên bản:** tính năng công khai vẫn có thể có ràng buộc mới; tùy chọn chẩn đoán và tính năng thử nghiệm có thể đổi hoặc bị loại bỏ. Ưu tiên JLS/JVMS/API spec và hướng dẫn VM chính thức của phiên bản đang dùng.

### Một tình huống thiết kế

Nhóm phát triển viết thư viện trả về `List.copyOf(input)` và vận hành dịch vụ trên HotSpot với G1. Thư viện **được phép** cam kết trả về danh sách không thể sửa theo API Java SE; thư viện **không nên** cam kết số mili giây dừng GC hoặc yêu cầu người dùng truyền `-XX:+UseG1GC`. Nhóm vận hành có thể bật G1 nếu HotSpot đang dùng hỗ trợ, đo thông số rồi điều chỉnh độc lập với hợp đồng API của thư viện. Khi chuyển JVM, phần phụ thuộc Java SE tiếp tục có cơ sở tương thích; phần tuning phải xem lại.

## 7. Tự kiểm tra

1. **“`var` tạo kiểu động mới trong JVM.”** Sai. Đây là suy luận kiểu tĩnh khi biên dịch theo Java SE; kiểu suy ra được kiểm tra bình thường.
2. **“Java SE 10 quy định `List.copyOf`, nên mọi bản triển khai trả về cùng lớp nội bộ.”** Sai. Hợp đồng API chuẩn hóa hành vi, không chuẩn hóa lớp hiện thực.
3. **“Java 10 có JEP 307, nên mọi JVM hỗ trợ Java 10 phải dùng G1 parallel full GC.”** Sai. Đây là cải tiến của HotSpot.
4. **“Mã ứng dụng cần CDS archive mới được chạy đúng.”** Sai. CDS/AppCDS là tối ưu hóa môi trường chạy; ứng dụng đúng không phụ thuộc archive.
5. **“Cùng một JEP có thể thuộc phạm vi khác nhau: ngôn ngữ hoặc implementation.”** Đúng. Phải kiểm tra đặc tả và mô tả/scope của từng JEP.
6. **“Tối ưu hóa GC/JIT không bao giờ cần kiểm thử.”** Sai. Dù không làm đổi hợp đồng ngôn ngữ/API, chúng vẫn có tác động về độ trễ, CPU và bộ nhớ cần đo trong môi trường thực.

## 8. Tài liệu chuẩn để tra cứu

- [Java SE & JDK Specifications (ví dụ Java SE 27)](https://docs.oracle.com/en/java/javase/27/docs/specs/index.html): cổng tra JLS, JVMS, API Specification và tài liệu JDK Tool.
- [JEP 286 — Local-Variable Type Inference](https://openjdk.org/jeps/286): thay đổi ngôn ngữ đưa vào Java 10.
- [Java SE API — List.copyOf, Since 10](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/List.html): hợp đồng API còn dùng trong JDK hiện đại.
- [JEP 307 — Parallel Full GC for G1](https://openjdk.org/jeps/307): thay đổi HotSpot/GC.
- [JEP 310 — Application Class-Data Sharing](https://openjdk.org/jeps/310): tối ưu hóa lưu/khởi tạo metadata lớp.
- [JEP 312 — Thread-Local Handshakes](https://openjdk.org/jeps/312) và [JEP 304 — Garbage Collector Interface](https://openjdk.org/jeps/304): thay đổi bên trong VM.
- [Java Virtual Machine Guide — Class Data Sharing](https://docs.oracle.com/en/java/javase/25/vm/class-data-sharing.html): cách hiểu CDS trong JDK hiện đại; kiểm tra tài liệu đúng phiên bản khi cấu hình.
- [System API documentation](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/System.html): định nghĩa các system property về đặc tả và bản triển khai.

**Nguyên tắc ghi nhớ:** Hỏi “điều này nằm trong JLS, JVMS hoặc Java SE API Specification không?” để xác định cam kết nền tảng; nếu là thuật toán GC, JIT, tùy chọn `-XX`, archive hoặc cơ chế nội bộ, hãy kiểm chứng trong tài liệu triển khai HotSpot/JDK hiện tại.