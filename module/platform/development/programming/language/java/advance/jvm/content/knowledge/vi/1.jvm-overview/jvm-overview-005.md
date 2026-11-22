# Phân biệt đặc tả JVMS, dự án OpenJDK và cách triển khai HotSpot

## Mục tiêu và bức tranh tổng thể

Khi nói “JVM chạy chương trình Java”, cần phân biệt **ba lớp có vai trò khác nhau**:

1. **JVMS (Java Virtual Machine Specification)** là **đặc tả**: mô tả máy ảo trừu tượng, định dạng class file, tập lệnh bytecode, các vùng dữ liệu và quy tắc thực thi mà một JVM tương thích phải tuân theo.
2. **OpenJDK** là **dự án/mã nguồn mở** phát triển một bộ JDK: có trình biên dịch Java (`javac`), công cụ (`java`, `javap`, `jcmd`...), thư viện Java và một cách triển khai JVM thường đi kèm là HotSpot.
3. **HotSpot** là **một cách triển khai JVM cụ thể**, nổi bật trong các bản dựng JDK dựa trên OpenJDK. Nó hiện thực các hành vi do JVMS yêu cầu, đồng thời tự chọn cơ chế thực thi và tối ưu, chẳng hạn thông dịch, JIT, bộ thu gom rác và quản lý bộ nhớ.

Hình dung theo luồng:

~~~text
Quy định về ngữ nghĩa JVM:
  Java Virtual Machine Specification (JVMS)
             |
             | Đặt ra hợp đồng tương thích
             v
Dự án mã nguồn triển khai JDK:
  OpenJDK: javac + java launcher + thư viện + HotSpot + công cụ...
             |
             | Đóng gói thành bản dựng JDK của một nhà cung cấp
             v
Ứng dụng:
  HelloJvm.java --(javac)--> HelloJvm.class --(HotSpot JVM)--> Kết quả

Lưu ý: một triển khai JVM khác cũng có thể tuân thủ JVMS.
~~~

**Phân biệt quan trọng:** JVMS không phải chương trình có thể cài đặt; OpenJDK không phải tên của một thuật toán chạy bytecode; HotSpot không phải tên chính thức của đặc tả JVM.

## 1. JVMS: bản hợp đồng của máy ảo

### JVMS quy định những gì?

JVMS mô tả **máy ảo trừu tượng**, không ấn định một cấu trúc phần mềm hay phần cứng duy nhất. Các nhóm quy tắc cốt lõi gồm:

- **Định dạng `.class`:** magic number `0xCAFEBABE`, phiên bản class file, constant pool, thông tin lớp, phương thức, trường, thuộc tính và mã lệnh. JVM phải nhận diện và diễn giải class file phù hợp phiên bản nó hỗ trợ.
- **Hệ kiểu và tập bytecode:** kiểu nguyên thủy, tham chiếu, các thao tác như `iload`, `iadd`, `invokevirtual`, `new`, `return`; trạng thái operand stack/local variables và tác động của lệnh.
- **Nạp, liên kết, khởi tạo lớp:** các quy tắc về loading, verification, preparation, resolution, initialization và lỗi liên quan. Thời điểm resolution có thể linh hoạt trong khuôn khổ đặc tả.
- **Run-time data areas:** những khái niệm như **heap**, **method area**, **run-time constant pool**, **JVM stack**, **PC register** và **native method stack**. Một số vùng chung cho các thread; một số thuộc mỗi thread.
- **Thực thi phương thức, ngoại lệ và đồng bộ:** cách frame hình thành/kết thúc, gọi và trả về từ phương thức, ném và xử lý ngoại lệ, ngữ nghĩa của `monitorenter`/`monitorexit`.
- **Các ràng buộc tương thích:** điều gì là hành vi quan sát được mà một JVM hợp lệ phải bảo đảm; điều gì có thể dẫn đến lỗi xác minh hoặc liên kết.

Ví dụ: JVMS mô tả việc `iadd` lấy hai giá trị `int` trên operand stack, cộng theo quy tắc số nguyên Java rồi đẩy kết quả. JVMS **không bắt buộc** nhà phát triển JVM phải viết đoạn xử lý bằng C++, bằng assembly hay tạo một lệnh máy tương ứng cho mỗi `iadd`.

### JVMS không quy định những gì?

Nhiều chi tiết vận hành là lựa chọn của nhà triển khai:

- JVM có **thông dịch**, **JIT** hay kết hợp các kỹ thuật hay không; mức tối ưu mã máy và cách bố trí trình biên dịch JIT.
- Bộ thu gom rác là G1, ZGC hay thuật toán khác; chính sách pause, số luồng GC và bố cục vùng nhớ cụ thể.
- Đối tượng được đặt trong RAM thế nào, header đối tượng dài bao nhiêu, con trỏ có nén không, method area được ánh xạ lên vùng nhớ vật lý nào.
- Các cờ triển khai như `-XX:+PrintCompilation`, `-XX:MaxRAMPercentage=...`, cấu trúc tệp log riêng, phần lớn giao diện chẩn đoán.
- Định dạng gói cài JDK, hãng phát hành, lịch cập nhật, hệ điều hành/CPU được hỗ trợ.

Nói **“JVMS yêu cầu có heap”** là đúng; nói **“JVMS yêu cầu heap được chia thành những vùng giống G1”** là sai. JVMS yêu cầu cơ chế thu hồi bộ nhớ tự động cho đối tượng, nhưng không ấn định thuật toán GC. Tương tự, **method area** là khái niệm do JVMS quy định, còn **Metaspace** là chi tiết triển khai quen thuộc của HotSpot, không phải một vùng nhớ được JVMS đặt tên bắt buộc.

### JVMS khác JLS và Java SE API ở đâu?

| Tài liệu/khái niệm | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| **JLS – Java Language Specification** | Chương trình nguồn Java hợp lệ có cú pháp, kiểu và ngữ nghĩa thế nào? | `class`, overload, generics, cách tính biểu thức trong Java |
| **JVMS – Java Virtual Machine Specification** | Class file và bytecode được biểu diễn, xác minh và thực thi thế nào? | `constant_pool`, `iload`, `invokevirtual`, stack frame |
| **Java SE API specification** | Các thư viện chuẩn hứa cung cấp API/hành vi gì? | `java.lang.String`, `java.util.List`, `System.out.println` |
| **JDK implementation** | Ai viết compiler, thư viện và VM để thực hiện các hợp đồng đó? | Mã nguồn OpenJDK và các bản dựng dựa trên nó |

`System.out.println` là lời gọi **thư viện Java** có đặc tả API; bytecode `getstatic`/`invokevirtual` có ngữ nghĩa theo JVMS; việc thực sự viết ký tự ra console còn phụ thuộc thư viện chuẩn và môi trường I/O. Không nên gán toàn bộ hành vi Java SE cho riêng JVMS.

## 2. OpenJDK: dự án xây dựng bộ công cụ Java

### OpenJDK là gì?

**OpenJDK** là hệ sinh thái phát triển mã nguồn mở cho các triển khai nền tảng Java SE và các thành phần liên quan. Dự án JDK tập hợp nhiều thành phần để tạo nên **JDK (Java Development Kit)**, ví dụ:

- **`javac`**: biên dịch mã nguồn `.java` thành bytecode/class file.
- **`java`**: launcher khởi động chương trình, thiết lập môi trường thực thi và sử dụng VM có trong bản dựng.
- **HotSpot VM**: triển khai máy ảo trong phần lớn bản dựng OpenJDK thông dụng.
- **Class libraries/modules**: ví dụ `java.base`, `java.logging`, `java.net.http`.
- **Công cụ phát triển/chẩn đoán**: `javap`, `jar`, `javadoc`, `jcmd`, `jstack`, `jfr` (phụ thuộc bản dựng và phiên bản).

Dự án không đồng nghĩa với **một bản cài duy nhất trên máy**. Nhiều nhà cung cấp tạo các bản dựng từ mã OpenJDK, có thể khác nhau về bản vá, lịch hỗ trợ, chứng nhận tương thích, giấy phép/điều khoản phân phối, cấu hình và nền tảng hỗ trợ. Vì thế, **OpenJDK** có thể chỉ dự án nguồn, hoặc được dùng trong tên một bản dựng JDK; phải nhìn ngữ cảnh.

Một bản dựng “dựa trên OpenJDK” không tự động chứng minh rằng mọi cấu hình, extension hoặc hiệu năng của nó giống hệt tất cả bản dựng khác. Cũng không nên suy ra “Oracle JDK” và “OpenJDK” là hai đặc tả ngôn ngữ/máy ảo khác nhau: chúng là những cách phân phối/sản phẩm trong hệ sinh thái Java và có lịch sử, điều khoản cụ thể theo phiên bản.

### Khi dùng OpenJDK, thành phần nào làm việc?

Với một ứng dụng Java bình thường:

1. `javac` phân tích mã nguồn theo quy tắc ngôn ngữ Java và phát sinh class file tuân theo JVMS.
2. Công cụ `java` khởi chạy runtime và VM được đóng gói trong bản JDK đang dùng.
3. VM nạp/xác minh/liên kết/khởi tạo các lớp phù hợp, thực hiện bytecode; thư viện Java cung cấp hành vi của các API được chương trình gọi.
4. Khi chạy, VM có thể thông dịch và tối ưu code; có thể gọi mã native, sử dụng dịch vụ hệ điều hành và quản lý tài nguyên.

Có thể lập trình **Kotlin, Scala** hoặc ngôn ngữ khác tạo class file cho JVM; ở bước thực thi, ranh giới chính là **JVMS**, dù trình biên dịch nguồn ban đầu không phải `javac`.

### Mã nguồn OpenJDK nằm ở đâu?

Repository phát triển JDK chính: [github.com/openjdk/jdk](https://github.com/openjdk/jdk). Các thư mục hữu ích để tra cứu:

- `src/hotspot/`: phần VM HotSpot, gồm runtime, class file handling, JIT, GC, hỗ trợ CPU/hệ điều hành.
- `src/java.base/`: nhiều lớp nền tảng và thư viện native hỗ trợ.
- `src/jdk.compiler/`: các thành phần của compiler Java.
- `src/jdk.jcmd/`: công cụ phục vụ chẩn đoán.

Đây là cấu trúc mã nguồn triển khai, **không phải** cấu trúc được JVMS bắt buộc. Thư mục/cơ chế có thể thay đổi theo nhánh và phiên bản.

## 3. HotSpot: JVM hoạt động thực tế ra sao?

**HotSpot** là tên một triển khai JVM được phát triển trong OpenJDK. Trong một bản dựng sử dụng HotSpot, VM bảo đảm hành vi được JVMS yêu cầu và cung cấp thêm các cơ chế tối ưu, quản trị tài nguyên, chẩn đoán.

### Các thành phần chính

**Nạp và chuẩn bị thực thi lớp.** HotSpot tham gia vào tải class file, kiểm tra tính hợp lệ bytecode, liên kết và khởi tạo theo quy tắc JVMS. Những lớp có thể đến từ file, module, JAR, bộ nạp tùy biến hay nguồn sinh động; không nên hiểu JVM chỉ chạy những file `.class` được lưu sẵn trên ổ cứng.

**Bộ máy thực thi.** HotSpot có **interpreter** để thực thi bytecode và các **JIT compiler** nhằm biên dịch những vùng mã thích hợp thành machine code. Trong nhiều cấu hình server, HotSpot dùng **tiered compilation** (thường gồm C1/C2) để cân bằng thời gian khởi động, thu thập profile và hiệu năng ổn định. Chi tiết compiler/tầng tối ưu có thể khác theo phiên bản/cấu hình; JVMS không yêu cầu JIT.

**Quản lý bộ nhớ và garbage collection.** HotSpot cấp phát đối tượng, theo dõi các tham chiếu cần thiết cho GC và cung cấp những collector như **G1** và **ZGC** trên các phiên bản/nền tảng hỗ trợ. Các cấu trúc như **Metaspace**, code cache, TLAB, card table hoặc region đều là chi tiết của một cách triển khai; không nên coi chúng là tên bắt buộc trong JVMS.

**Luồng, đồng bộ và tương tác hệ điều hành.** HotSpot triển khai cơ chế thread, monitor, JNI, điều phối runtime, giao tiếp OS và các điểm phối hợp cần cho tác vụ VM như GC. Kiểu ánh xạ thread và thuật toán khóa có thể tiến hóa mà vẫn phải giữ ngữ nghĩa JVM/Java đúng quy định.

**Quan sát và cấu hình.** HotSpot có công cụ, flag, log GC/JIT và cơ chế diagnostic; các cờ `-X`/`-XX` là giao diện vận hành theo triển khai, có thể thay đổi, bị giới hạn hoặc không xuất hiện trên JVM khác.

### Ví dụ: cùng một phép cộng, nhiều con đường chạy

Giả sử bytecode có `iload_1`, `iload_2`, `iadd` và `ireturn`:

- JVMS định nghĩa các bước trừu tượng và giá trị kết quả của phép cộng `int`.
- HotSpot có thể chạy bằng interpreter ở thời điểm đầu.
- Nếu phương thức phù hợp để tối ưu, HotSpot có thể biên dịch thành mã máy và chạy mã đó trong những lần sau; cách dịch không nhất thiết tương ứng từng bytecode với một lệnh CPU.
- Dù chọn đường nào, chương trình phải quan sát được ngữ nghĩa mà đặc tả đòi hỏi (trừ các hành vi được đặc tả cho phép linh hoạt).

HotSpot có thể **deoptimization** (quay về dạng thực thi tổng quát khi một giả định tối ưu không còn đúng). Đây là chiến lược nội bộ để tối ưu hiệu năng nhưng vẫn giữ ngữ nghĩa, không phải câu lệnh bytecode mới do JVMS bắt buộc.

## 4. Bảng so sánh ba khái niệm

| Tiêu chí | JVMS | OpenJDK | HotSpot |
| --- | --- | --- | --- |
| Bản chất | Tài liệu đặc tả chuẩn của máy ảo | Dự án/cơ sở mã nguồn xây JDK | Một triển khai JVM cụ thể |
| Câu hỏi chính | “VM phải làm gì và bảo đảm điều gì?” | “Mã nguồn/công cụ/thư viện để xây JDK ở đâu?” | “VM cụ thể thực hiện và tối ưu thế nào?” |
| Có thể chạy trực tiếp? | Không | “Dự án” không chạy; **bản dựng JDK** chứa chương trình/công cụ chạy được | Có, khi được đóng gói trong runtime |
| Phạm vi | Class file, bytecode, các quy tắc VM | Compiler, thư viện, launcher, VM, công cụ, quy trình dự án | Runtime VM, JIT, GC, memory, threads, diagnostics |
| Ví dụ | Heap và operand stack là khái niệm bắt buộc | `javac`, `java.base`, repository `openjdk/jdk` | C1/C2, G1/ZGC, Metaspace, các cờ `-XX` |
| Thay thế được bằng gì? | Phiên bản đặc tả khác tùy release; phải xét tương thích | Một dự án/bản phân phối Java SE khác | Một JVM tương thích khác, ví dụ Eclipse OpenJ9 |
| Cách tra cứu | Chương định nghĩa trong JVMS đúng phiên bản | Tài liệu dự án, mã nguồn, release notes | Tài liệu HotSpot, flag/help, nguồn `src/hotspot`, log |

Mối quan hệ cần nhớ: **HotSpot là một thành phần triển khai được dùng trong OpenJDK; OpenJDK cung cấp nguồn và công cụ của một JDK; JVMS đặt ra hợp đồng cho JVM.** Ba tên thuộc ba loại đối tượng khác nhau, không phải ba sản phẩm chạy song song và cũng không phải ba bước “biên dịch” tuần tự.

## 5. Thực hành: từ Java source tới JVM đang chạy

Ví dụ dùng Java 17+; tạo file `HelloJvm.java` (tên file trùng `public class`):

~~~java
public class HelloJvm {
    public static void main(String[] args) {
        int total = 3 + 4;
        System.out.println("Tong = " + total);
        System.out.println("VM = " + System.getProperty("java.vm.name"));
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~bash
javac HelloJvm.java
javap -c HelloJvm
java HelloJvm
java -version
~~~

Đầu ra chương trình **chắc chắn** có dòng đầu:

~~~text
Tong = 7
~~~

Dòng thứ hai bắt đầu bằng `VM = `, nhưng **giá trị phụ thuộc bản JDK/VM**. Ví dụ ở nhiều bản dựng HotSpot Server VM, dòng đó chứa tên như `OpenJDK 64-Bit Server VM`; đừng sao chép tên này thành kết quả chung cho mọi máy. Lệnh `java -version` cho biết thông tin phiên bản/runtime/VM do bản dựng công bố; định dạng và tên hãng cũng có thể khác.

Lệnh `javap -c HelloJvm` cho phép xem bytecode của class file. Với đoạn in chuỗi và gọi API, bạn có thể thấy các lệnh như `getstatic` (đọc `System.out`), `invokevirtual` (gọi `println`), `ldc` hoặc `invokedynamic` (tùy cách compiler tạo nối chuỗi), cùng các lệnh trả về. **Không** coi số thứ tự constant pool hoặc toàn bộ disassembly là cố định qua mọi bản compiler; JVM chỉ phải tuân theo cấu trúc/ngữ nghĩa class file mà nó chấp nhận.

### Liên hệ từng hành động với từng lớp

| Bước nhìn thấy | Lớp liên quan | Vì sao? |
| --- | --- | --- |
| `javac HelloJvm.java` tạo `HelloJvm.class` | OpenJDK/JDK tool + JLS/JVMS | Compiler là chương trình thực; bytecode xuất ra phải theo class-file contract |
| `javap -c` in lệnh bytecode | JDK tool + JVMS | Lệnh mang ý nghĩa theo tài liệu JVMS |
| `java HelloJvm` chạy chương trình | Launcher trong JDK + HotSpot hoặc VM được đóng gói | JVM cụ thể thực thi class, thư viện cung cấp `System.out` |
| `java.vm.name` | Runtime đang sử dụng | Quan sát tên VM được nhà triển khai khai báo, không phải cách xác minh toàn bộ tính tương thích |
| G1, JIT, log GC, `-XX` | Chủ yếu HotSpot | Chiến lược/cấu hình thực thi, không phải bytecode chuẩn |

### Một so sánh thêm trên HotSpot

Trong môi trường dùng HotSpot có hỗ trợ, bạn có thể thử:

~~~bash
java -Xint HelloJvm
~~~

Cờ `-Xint` yêu cầu HotSpot chạy theo chế độ thông dịch, thường hữu ích để đối chiếu hành vi/chẩn đoán. Kết quả chức năng vẫn là phép tính `3 + 4 = 7` và việc in VM name; tốc độ không nên suy ra từ chương trình quá nhỏ này. `-Xint` là tùy chọn của runtime cụ thể, **không phải câu lệnh hay yêu cầu trong JVMS**; VM khác có thể không hỗ trợ.

Nếu một tùy chọn chẩn đoán bị từ chối, trước hết hãy kiểm tra bản dựng, phiên bản và VM (`java -version`, tài liệu chính thức của hãng). Đừng suy luận rằng JVM đã vi phạm JVMS chỉ vì nó không biết một cờ `-XX` của HotSpot.

## 6. Chuẩn so với lựa chọn triển khai: cách phân loại tình huống

**Tình huống A — class file sai định dạng:** Khi gặp class file có cấu trúc không hợp lệ hoặc phiên bản không được hỗ trợ, hãy tra **JVMS – Class File Format/Verification** và thông báo lỗi cụ thể. Trước khi kết luận VM lỗi, cần đối chiếu phiên bản JDK và bytecode đang chạy.

**Tình huống B — ứng dụng bị `OutOfMemoryError`:** JVMS có quy tắc liên quan đến các vùng dữ liệu và `OutOfMemoryError`, nhưng để phân tích mức sử dụng bộ nhớ, heap dump, Metaspace và cách GC hoạt động trên máy thực tế, cần tra **HotSpot/runtime cụ thể**, cấu hình và log. Không đồng nhất kích thước heap với toàn bộ bộ nhớ process.

**Tình huống C — đổi collector G1 sang ZGC:** Đây là lựa chọn **của HotSpot/bản dựng runtime**. Chương trình Java không phải đổi bytecode vì JVMS không khóa ứng dụng vào một collector nhất định. Tuy vậy, hiệu năng/pause có thể thay đổi đáng kể.

**Tình huống D — thay JDK vendor:** So sánh release, bản vá bảo mật, nền tảng CPU/OS, API hỗ trợ, giấy phép, hỗ trợ thương mại và **VM đi kèm**. Không suy ra rằng cùng chữ “OpenJDK” bảo đảm mọi option JIT/GC giống nhau.

**Tình huống E — JVM khác chạy bytecode Java:** JVM tương thích có thể chọn cách quản lý bộ nhớ và tạo mã khác HotSpot. **Khả năng thực thi class file đúng hợp đồng** là trọng tâm của tính tương thích với JVMS; đặc trưng HotSpot không tự trở thành đặc tả.

## 7. Những hiểu nhầm phổ biến

1. **“OpenJDK chính là HotSpot.”** Chưa chính xác: HotSpot là một thành phần VM trong hệ mã nguồn JDK; OpenJDK còn có compiler, thư viện, launcher và nhiều công cụ.
2. **“JVMS quy định bắt buộc dùng JIT hoặc G1.”** Sai: JVMS quy định hành vi máy ảo, để nhà triển khai chọn cơ chế tối ưu và thuật toán quản lý bộ nhớ.
3. **“Metaspace = method area theo tên chính thức của đặc tả.”** Sai: method area là khái niệm JVMS; HotSpot có chi tiết lưu metadata như Metaspace.
4. **“Mọi bản OpenJDK đều có đúng những dòng `java -version` như nhau.”** Sai: build, vendor, phiên bản, OS/CPU và VM có thể khác nhau.
5. **“Mọi đặc tính của HotSpot đều dùng được ở JVM khác.”** Sai: cờ `-XX`, log, công cụ và tối ưu của HotSpot thường không phải API/ABI portable.
6. **“Có bytecode thì VM phải chạy được bất kể phiên bản.”** Sai: class file có version/feature, runtime cần hỗ trợ những phần tương ứng; lỗi `UnsupportedClassVersionError` thường phản ánh Java runtime cũ hơn class file.
7. **“JVM chính là Java.”** Sai: ngôn ngữ Java, nền tảng thư viện Java SE và máy ảo JVM liên quan chặt chẽ nhưng có đặc tả/phạm vi khác nhau.

## 8. Tự kiểm tra

**Câu 1.** Một tài liệu định nghĩa bytecode `invokevirtual`, frame và constant pool. Bạn đang đọc về khái niệm nào?  
**Đáp án:** JVMS, vì đây là các quy tắc về máy ảo và định dạng class file.

**Câu 2.** Bạn muốn sửa thuật toán GC hoặc tìm mã nguồn C++ chạy trong VM của bản dựng OpenJDK phổ biến. Nên bắt đầu ở đâu?  
**Đáp án:** Thành phần HotSpot, thường từ `src/hotspot`; tra đúng nhánh JDK đang dùng.

**Câu 3.** Bạn muốn xem code của `javac` và thư viện `java.base`. JVMS có cung cấp code đó không?  
**Đáp án:** Không. Đọc dự án OpenJDK/JDK source; JVMS là tài liệu quy định hành vi VM.

**Câu 4.** Một JVM xử lý bytecode đúng nhưng không hỗ trợ `-XX:+PrintCompilation`. Có đủ bằng chứng khẳng định vi phạm JVMS không?  
**Đáp án:** Không. `-XX` là tùy chọn triển khai; kiểm tra yêu cầu chuẩn liên quan trước khi đánh giá tính tương thích.

**Câu 5.** Khi chuyển từ HotSpot sang JVM khác, phần nào cần xem lại trước tiên?  
**Đáp án:** Các tùy chọn, công cụ, log, giả định hiệu năng/GC phụ thuộc HotSpot. Hành vi ứng dụng dựa trên Java SE/JVMS hợp lệ có tính di động cao hơn nhưng vẫn cần kiểm thử theo nền tảng và phiên bản.

## 9. Tài liệu đọc tiếp

- [Java Language and Virtual Machine Specifications](https://docs.oracle.com/javase/specs/) — chọn đúng phiên bản Java SE khi tra JVMS/JLS.
- [JVMS – The Structure of the Java Virtual Machine](https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-2.html) — máy ảo trừu tượng, run-time data areas, hướng dẫn phân biệt hợp đồng với triển khai.
- [JVMS – The Class File Format](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html) — cấu trúc class file và quy tắc định dạng; tra phiên bản tương ứng với runtime của bạn.
- [OpenJDK](https://openjdk.org/) và [OpenJDK JDK Project](https://openjdk.org/projects/jdk/) — dự án và hướng dẫn phát triển JDK.
- [OpenJDK JDK source](https://github.com/openjdk/jdk) — xem mã nguồn `src/hotspot`, `src/jdk.compiler`, `src/java.base`.

**Ghi nhớ khi đọc tiếp về JVM:** đặt câu hỏi “**đây là hợp đồng trong JVMS, mã nguồn từ dự án OpenJDK, hay một quyết định triển khai của HotSpot?**”. Phân loại đúng ngay từ đầu sẽ giúp bạn tra đúng tài liệu và tránh nhầm đặc tính của một VM với yêu cầu bắt buộc cho mọi JVM.