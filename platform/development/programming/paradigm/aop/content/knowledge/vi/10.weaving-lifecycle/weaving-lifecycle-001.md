# Dệt khi biên dịch và yêu cầu đối với chuỗi xây dựng trong AOP

**Dệt khi biên dịch** (*compile-time weaving*, CTW) là cách kết hợp **aspect** với chương trình trong giai đoạn tạo mã thực thi. Công cụ biên dịch hoặc bộ dệt (*weaver*) sử dụng mã chương trình cơ sở, các định nghĩa aspect, pointcut, advice và thông tin kiểu để tạo **bytecode đã kết hợp hành vi bổ sung** ở những điểm can thiệp được hỗ trợ.

Điểm quan trọng nhất của bài: **weaving xảy ra ở thời điểm build; advice chạy về sau, khi chương trình thực thi một join point phù hợp**. Một aspect được khai báo trong nguồn không tự chạy. Việc biên dịch thành công chưa chứng minh artifact triển khai đã chứa bytecode được dệt; người xây dựng hệ thống còn phải kiểm soát chuỗi build, kiểm thử và đóng gói.

Bài trình bày **AOP cơ bản và nâng cao nói chung**, không gán chức năng của một công cụ riêng cho mọi hệ AOP. Những khả năng như field get/set, constructor, method call, method execution, binding và thứ tự advice phụ thuộc mô hình join point cùng công cụ dệt cụ thể.

## 1. Sau bài học cần hiểu gì?

- Đầu vào của compile-time weaving gồm những gì; thông tin nào là bắt buộc và thông tin nào phụ thuộc công cụ.
- Bộ dệt tạo ra gì: file class, bytecode, artifact; vì sao không nhất thiết phải sửa file Java gốc.
- Sự khác nhau giữa **compile-time**, **post-compile/binary**, **load-time** và **runtime proxy composition**.
- Cách thiết kế pipeline để chỉ sử dụng **output đã weave** trong integration test, packaging và triển khai.
- Cách cấu hình phạm vi lớp, dependency, classpath/module path, thứ tự aspect và mức JDK mục tiêu.
- Cách quản lý incremental build, cache, generated code, double weaving, dependency runtime và bản phát hành.
- Cách chứng minh pointcut khớp đúng nơi và advice thực sự được kích hoạt mà không đổi hợp đồng nghiệp vụ.
- Những lỗi phổ biến khi build báo thành công nhưng chương trình không có advice.

## 2. Bản đồ kiến trúc weaving

```text
    Base source / bytecode        Aspect definitions
              |                   Pointcut + Advice
              |                          |
              +-------------+------------+
                            |
               Dependencies / type model
               Compiler, weaver, configuration
                            |
                            v
                   COMPILE + WEAVE
                            |
                            v
                     WOVEN CLASSES
                            |
                  Test -> Package -> Deploy
                            |
                            v
                        JVM RUNS
                            |
                 Matching join point?
                         /     \
                       No       Yes
                       |         |
                 No advice   Advice executes
```

Đây là sơ đồ **trách nhiệm logic**, không phải thuật toán cố định của một weaver. Khi công cụ tích hợp trực tiếp vào compiler, compile và weave có thể nằm trong một bước. Khi xử lý bytecode sau biên dịch, compiler và weaver là hai bước khác nhau.

| Thành phần | Trách nhiệm |
| --- | --- |
| **Base program** | Mã có chức năng nghiệp vụ cần giữ nguyên hợp đồng |
| **Aspect** | Khía cạnh biểu diễn chính sách cắt ngang |
| **Pointcut** | Chọn join point theo loại, chữ ký, kiểu, phạm vi, bối cảnh |
| **Advice** | Hành vi trước/sau/bao quanh điểm được chọn |
| **Join point model** | Quy định những điểm nào thực sự có thể can thiệp |
| **Weaver** | Kết hợp hành vi aspect vào kết quả biên dịch |
| **Weaving configuration** | Xác định đầu vào, include/exclude, thứ tự, tùy chọn |
| **Woven output** | Mã chạy đã có cơ chế để kích hoạt advice |
| **Runtime** | Nơi lời gọi xảy ra và advice thực sự được chạy |

Một lớp có thể được dệt thành công nhưng không có lời gọi nào chạm join point. Vì vậy **số lớp được weave khác số lần advice chạy**.

## 3. Những đầu vào của compile-time weaving

### 3.1. Chương trình cơ sở

Một lớp Java thường:

```java
package example.order;

public final class OrderService {
    public String submit(String id) {
        return "ORDER:" + id;
    }
}
```

Đây là **một tệp lớp độc lập** đặt ở `example/order/OrderService.java`, chưa có `main`. Một pointcut có thể muốn chọn thực thi `submit(String)`; một pointcut khác có thể chọn các **lời gọi** đến phương thức đó.

Điểm **method execution** có vị trí ở phương thức đích, còn điểm **method call** có thể nằm ở mã chứa lời gọi phía người gọi. Nếu chỉ đưa một phía vào tập mã được weave, tập điểm can thiệp thực sự có thể khác nhau. Không nên xem hai loại điểm là tương đương.

### 3.2. Định nghĩa aspect

Aspect thường chứa bộ lọc pointcut, một hoặc nhiều advice và đôi khi có trạng thái/precedence. Ví dụ mục tiêu kiến trúc:

```text
Chọn: thực thi example.order.OrderService.submit(String)
Trước: ghi thời điểm bắt đầu
Sau trả về: ghi thời lượng thành công
Sau lỗi: ghi loại ngoại lệ
Luôn dọn: khôi phục bối cảnh đo lường đã mở
```

Đây là **đặc tả ý tưởng**, không phải cú pháp AOP hay Java trực tiếp. Một công cụ thật phải cung cấp cú pháp có khả năng mô tả các điểm đó và cách binding dữ liệu.

### 3.3. Thông tin kiểu và thư viện phụ thuộc

Để biết pointcut có khớp không, weaver có thể cần:

- Định nghĩa lớp, superclass, interface và chữ ký;
- Modifier, annotation và kiểu tham số/return;
- Mã hoặc thư viện mà advice gọi tới;
- Classpath hoặc module path để phân giải kiểu;
- Phiên bản compiler, weaver và mục tiêu bytecode/JVM.

Nếu thiếu classpath, áp sai phiên bản dependency hoặc dùng phiên bản weaver không hỗ trợ mức bytecode đầu vào, build có thể lỗi hoặc tạo artifact không phù hợp. Tên cờ cấu hình rất khác nhau; **`javac` thông thường không tự hiểu một ngôn ngữ pointcut chuyên biệt chỉ vì có file aspect trong thư mục nguồn**.

### 3.4. Cấu hình include/exclude và precedence

Một chính sách chỉ dành cho cổng xử lý đơn hàng không nên tác động toàn bộ mã logging, serialization hoặc thư viện ngoài. Build cần biết tập lớp/bytecode nằm trong phạm vi công cụ xử lý. Bộ lọc pointcut lại quyết định **join point nào trong phạm vi ấy được chọn**.

Nếu một class không nằm trong tập đầu vào weave, pointcut đúng tên của nó cũng chưa có hiệu lực. Nếu một lớp có nhiều aspect khớp, thứ tự có thể đổi ý nghĩa, chẳng hạn:

```text
Timer(Retry(Operation))  -> đo cả chuỗi retry
Retry(Timer(Operation))  -> đo mỗi lần thử nếu Timer chạy trong retry
```

Thứ tự không nên được suy từ tên file; phải dùng quy tắc/cấu hình precedence của công nghệ và kiểm thử.

## 4. Đầu ra thực sự của compile-time weaving

Đầu ra thường là các file `.class` đã mang logic bổ sung, có thể được gói vào `.jar` hoặc artifact khác. Mã nguồn nghiệp vụ có thể **không bị sửa**, và cách weaver tổ chức bytecode không nhất thiết giống việc chèn thẳng câu `println` vào thân phương thức.

```text
Source + Aspect + Config
          |
          v
 AOP-aware compiler/weaver
          |
          +--> Woven .class files
                         |
                         v
                     Application JAR
                         |
                         v
                        JVM
```

Cần tách hai khái niệm:

- **Đầu ra trung gian**: thư mục class hoặc bytecode ngay sau bước weaving.
- **Đầu ra triển khai**: JAR, image hoặc gói ứng dụng cuối cùng có những class sẽ được JVM nạp.

Dự án có thể chạy bước weaving thành công nhưng đóng gói nhầm thư mục class gốc. Khi đó application JAR vẫn chạy được nghiệp vụ, song thiếu advice.

### 4.1. Không nhất thiết phải tồn tại lớp proxy

Khi CTW thực sự biến đổi bytecode ở method execution, một lời gọi tới đối tượng đích có thể đi qua logic đã dệt ngay tại phương thức đó theo mô hình công cụ. Điều này khác JDK dynamic proxy, nơi người gọi phải giữ đối tượng đại diện thay vì đối tượng gốc.

Tuy nhiên, **CTW không tự bảo đảm mọi điểm can thiệp**. Mô hình AOP, input class và loại join point vẫn giới hạn tập tác động.

### 4.2. Đã weave khác đã kích hoạt advice

Có thể xảy ra:

```text
Aspect defined:        YES
Pointcut resolved:     YES
Woven class generated: YES
Join point executed:   NO
Advice invoked:        NO
```

Hoặc join point đã xảy ra nhưng một điều kiện runtime trong pointcut không thỏa. Việc bytecode đã chứa logic kiểm tra động không có nghĩa advice phải chạy cho mọi lượt thực thi.

## 5. Các thời điểm dệt dễ nhầm với nhau

| Kiểu kết hợp | Thời điểm | Đầu vào chính | Đầu ra chủ yếu |
| --- | --- | --- | --- |
| **Compile-time weaving** | Trong bước compiler/weaver hiểu mã nguồn/aspect | Base source, aspect, thông tin kiểu | Class/artifact đã weave |
| **Post-compile/binary weaving** | Sau compiler thường, trước sử dụng artifact | Class đã biên dịch, aspect | Binary đã biến đổi |
| **Load-time weaving** | Trước khi JVM định nghĩa lớp | Bytecode lúc nạp, transformer/config | Class definition đã biến đổi trong JVM |
| **Runtime proxy/interceptor** | Lúc tạo/lắp đại diện | Đối tượng, giao diện/lớp, interceptor | Proxy/đường gọi được bao quanh |

Điểm chung của compile-time và binary weaving là **có thể chuẩn bị artifact trước runtime**. Điểm khác: binary weaving xử lý bytecode sau một bước biên dịch trước đó, còn CTW tích hợp thao tác weave trong quá trình biên dịch.

Load-time weaving có vấn đề riêng về class loader, thời điểm lớp được định nghĩa và khả năng biến đổi lớp đã nạp. Runtime proxy có vấn đề về **ai giữ tham chiếu proxy**. Không dùng những giới hạn của proxy để kết luận giới hạn cho tất cả hình thức CTW.

## 6. Chuỗi xây dựng đúng: đầu vào tới triển khai

Một pipeline có thể được mô hình hóa:

```text
1. Resolve toolchain/dependencies
2. Compile and weave the designated inputs
3. Verify woven output and run woven tests
4. Package ONLY the intended woven classes
5. Verify packaged artifact
6. Publish, deploy, run smoke tests
```

Đây là **giả mã quy trình**, không phải lệnh của một hệ build cụ thể. Nếu công cụ dùng binary weaving tách riêng, bước thứ 2 thành:

```text
compile base -> create original classes -> binary weave -> woven classes
```

Với CTW tích hợp, bước `compileAndWeave` có thể là một task. Điều kiện quan trọng: **task kiểm thử AOP và task đóng gói phải phụ thuộc vào đầu ra đã weave**, không phụ thuộc song song vào original classes.

### 6.1. Sai đồ thị phụ thuộc

Đồ thị nguy hiểm:

```text
compile -----+----> package
             |
             +----> weave
```

Ở đây `package` có thể chạy mà không đợi `weave`. Cấu trúc mong muốn:

```text
compile / weave ---> woven tests ---> package ---> artifact checks
```

Hoặc trong build hai bước:

```text
compile ---> weave ---> woven tests ---> package
```

Một bước test nghiệp vụ thuần có thể chạy sớm; nhưng không thể thay cho **integration test trên lớp đã weave**.

### 6.2. Ví dụ cấu trúc thư mục, không phải quy ước bắt buộc

```text
project/
  src/main/java/
  src/main/aspects/
  build/classes-original/
  build/classes-woven/
  build/dist/application.jar
```

Các đường dẫn này chỉ để hình dung đường dữ liệu. Không phải công cụ nào cũng dùng tệp aspect riêng hoặc hai thư mục class. Khi có cả bản gốc và bản woven, cần đánh dấu **chính xác task đọc/ghi từng thư mục** và bảo đảm packaging lấy đúng nguồn.

### 6.3. Test nên chạy ở đâu?

Một tầng unit test có thể kiểm tra business logic chưa weave để chẩn đoán dễ hơn. Nhưng phải có test dùng **class sau weave** để kiểm tra advice; khi đóng gói xong nên có smoke/integration test chạy **artifact cuối** trong môi trường runtime tương thích.

Chỉ thấy unit test của base class pass không có nghĩa một around advice mới sẽ giữ nguyên kết quả và ngoại lệ.

## 7. Ví dụ Java 17: mô hình hành vi đầu ra đã dệt

**Lưu ý:** JDK 17 `javac` thông thường không cung cấp một trình biên dịch pointcut tổng quát. Ví dụ sau **viết tay mô hình kết quả logic sau weaving**, để học về điều kiện bảo toàn và thứ tự advice. Nó không tự thực hiện CTW và không chứng minh weaver thực nào tạo cùng cấu trúc wrapper.

Lưu nội dung thành `CompileWeavingIllustration.java`:

```java
public class CompileWeavingIllustration {
    static final class OrderService {
        String submit(String id) {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("invalid id");
            }
            return "ORDER:" + id;
        }
    }

    // Mô hình hóa hành vi mà đầu ra đã kết hợp có thể thể hiện.
    static final class WovenOrderService {
        private final OrderService target = new OrderService();

        String submit(String id) {
            String shown = id == null ? "<null>"
                    : id.isBlank() ? "<blank>" : id;
            System.out.println("[BEFORE] " + shown);
            try {
                String result = target.submit(id);
                System.out.println("[RETURN] " + result);
                return result;
            } catch (RuntimeException error) {
                System.out.println("[THROW] "
                        + error.getClass().getSimpleName());
                throw error;
            } finally {
                System.out.println("[FINALLY]");
            }
        }
    }

    public static void main(String[] args) {
        OrderService original = new OrderService();
        WovenOrderService woven = new WovenOrderService();

        System.out.println("BASE " + original.submit("A"));
        System.out.println("WOVEN " + woven.submit("B"));

        try {
            woven.submit(" ");
        } catch (IllegalArgumentException error) {
            System.out.println("CALLER_ERROR " + error.getMessage());
        }

        System.out.println("END");
    }
}
```

Chạy với Java 17+:

```bash
javac -encoding UTF-8 CompileWeavingIllustration.java
java CompileWeavingIllustration
```

Kết quả:

```text
BASE ORDER:A
[BEFORE] B
[RETURN] ORDER:B
[FINALLY]
WOVEN ORDER:B
[BEFORE] <blank>
[THROW] IllegalArgumentException
[FINALLY]
CALLER_ERROR invalid id
END
```

**Phân tích:** Trong đoạn mô hình hóa, `OrderService` là hành vi gốc, còn `WovenOrderService` biểu diễn một kết quả có before, after-returning, after-throwing và finally. Khi tác vụ thành công, người gọi vẫn nhận `ORDER:B`. Khi đầu vào là khoảng trắng, người gọi vẫn nhận ngoại lệ `IllegalArgumentException`; nhánh `[RETURN]` không chạy, nhưng cleanup kiểu `finally` vẫn diễn ra.

Một weaver CTW thật có thể chèn bytecode trực tiếp vào lớp, không tạo `WovenOrderService` như ví dụ. **Dùng chương trình này để học hợp đồng đầu ra**, rồi kiểm chứng một công cụ thật bằng artifact và integration test của chính nó.

### 7.1. Test nào chứng minh CTW thật?

Không phải `javac` thành công với mã minh họa ở trên. Với một bộ dệt thật, cần:

1. Xác minh nó nhận định nghĩa aspect.
2. Xác minh điểm thực thi cần chọn nằm trong phạm vi weaving.
3. Xác minh output class/JAR sau weaving được tạo.
4. Chạy bản output ấy và khẳng định advice chạy ở điểm đúng.
5. Kiểm thử âm những điểm nằm ngoài pointcut.
6. Xác minh kết quả và ngoại lệ nghiệp vụ được giữ nếu advice chỉ quan sát.

Có thể dùng bytecode disassembler như `javap -c` để hỗ trợ tìm hiểu một class, nhưng hình dạng mã biến đổi phụ thuộc công cụ và bytecode tối ưu. Không nên dùng một mẫu lệnh máy duy nhất làm tiêu chí thành công cho mọi weaver.

## 8. Incremental build và bộ nhớ đệm

Ở những dự án lớn, build thường tái sử dụng output cũ. Với CTW, **định nghĩa aspect và cấu hình weaving phải được tính là đầu vào của task tạo class**.

Ví dụ: source của `OrderService` không đổi nhưng pointcut chuyển từ `submit(String)` sang mọi overload `submit(..)`. Nếu cache chỉ theo dõi thay đổi source nghiệp vụ, class được tái sử dụng có thể vẫn chứa logic advice cũ.

Các thay đổi có thể làm output không còn hợp lệ:

- Sửa thân advice;
- Thêm, xóa hoặc thu hẹp pointcut;
- Thay include/exclude, precedence;
- Đổi phiên bản weaver hoặc mức bytecode;
- Đổi dependency ảnh hưởng phân giải kiểu;
- Thêm overload hoặc lớp mới;
- Thay cấu trúc module/classpath.

### 8.1. Kiểm thử build sạch và build gia tăng

Một ma trận nhỏ:

| Thao tác | Kỳ vọng |
| --- | --- |
| Sửa advice, không sửa business class | Build tạo output chứa advice mới |
| Xóa aspect | Output mới không còn hành vi aspect bị xóa |
| Thêm overload | Pointcut khớp đúng overload theo chính sách |
| Đổi cấu hình exclude | Tập class được weave cập nhật |
| Clean build so với incremental cùng input | Hành vi quan sát tương đương |
| Đổi dependency/bytecode target | Toolchain phân giải lại tương thích |

Không cần tắt toàn bộ cache; cần khai báo đúng **input và output của bước weave**, cùng phép test xác minh.

## 9. Tránh double weaving và output hỗn hợp

Nếu một class đã được dệt lại bị đưa qua cùng công cụ lần nữa, nó có thể:

- Chứa logic advice trùng lặp;
- Có chuỗi chặn lồng nhau không chủ ý;
- Tăng kích thước bytecode hoặc chi phí;
- Hoặc bị công cụ phát hiện/từ chối.

Kết quả cụ thể phụ thuộc công cụ; **không mặc định mọi weaver có tính idempotent**. Thiết kế build nên có **một đường tạo output đã weave rõ ràng**, không để cả original và woven class cạnh tranh nhau trong classpath/packaging.

Một lỗi khác là trộn class từ build cũ và build mới vào cùng thư mục. Cần đảm bảo task dọn output hay kiểm tra tính đầy đủ không làm xóa nhầm dữ liệu ngoài phạm vi nhưng cũng không mang file class lỗi thời vào artifact.

## 10. Runtime dependencies và compatibility

Output đã weave có thể tham chiếu đến code của aspect, helper hoặc thư viện runtime của công nghệ AOP. Dependency có ở **compile/weaving classpath** chưa chắc đã có trong **runtime classpath**.

Dấu hiệu lỗi:

- Build và weaving đều thành công;
- JAR được tạo;
- Khi JVM nạp lớp hoặc chạy join point, xuất hiện `NoClassDefFoundError`, lỗi linkage hoặc lỗi cấu hình.

Cách kiểm tra là phân biệt:

- **Compiler/weaver tools** chỉ cần ở build;
- **Runtime support classes** có thể cần lúc chạy output đã weave;
- **Test helpers** chỉ cần ở test;
- **Dependencies của advice** có thể khác dependencies trực tiếp của base class.

Ngoài ra cần đảm bảo bytecode phù hợp mức JVM đích. Nếu xuất bytecode cho mức cao hơn JVM triển khai, ứng dụng có thể lỗi khi tải lớp dù bước weaving đã thành công.

### 10.1. Module và class loader

JPMS định nghĩa các quan hệ `requires`, `exports`, `opens`, nhưng không tự thực hiện weaving. Các hạn chế reflection, quyền truy cập/module, class loader và bytecode transformation phải được kiểm chứng theo JVM/công cụ thật.

Hai class cùng tên nhưng do hai loader khác nhau định nghĩa có thể là hai kiểu runtime riêng, nên tập lớp được weave và tập lớp chạy có thể không giống điều người thiết kế suy ra từ tên file.

## 11. Pointcut tĩnh, điều kiện động và độ phủ thực thi

Một weaver có thể phân tích chữ ký, package và kiểu tại build. Nhưng giá trị đối số, target instance và ngữ cảnh chạy chỉ có ở runtime. Công cụ có thể chèn bộ kiểm tra điều kiện động trước khi advice chạy.

```text
Build:  nhận diện điểm method execution phù hợp
        -> chèn logic cần thiết vào woven output

Runtime: phương thức được gọi
        -> kiểm tra điều kiện runtime (nếu có)
        -> advice chạy nếu đúng
```

Đừng kết luận “lớp đã weave” nghĩa là advice luôn chạy trong mọi lần gọi. Một điểm có thể:

- Không bao giờ được thực thi;
- Có điều kiện runtime không thỏa;
- Thuộc loại join point không được công cụ hỗ trợ thật;
- Không nằm trong artifact đã triển khai;
- Hoặc được chọn theo kiểu tĩnh khác dự kiến.

**Matched scope, woven output và effective advice invocation** là ba điều phải kiểm chứng riêng.

### 11.1. Kế thừa và overload

Nếu lớp có `submit(String)` và `submit(String,int)`, pointcut theo tên chung có thể khớp cả hai tùy cú pháp. Chọn chữ ký hẹp khi chính sách chỉ dành cho một overload.

Với lớp con, bridge method do compiler sinh hoặc generic erasure, tên/kiểu nhìn ở source có thể khác tập phương thức mức bytecode. Cần dùng diagnostics của công cụ và test trên đường thực thi thật, không kết luận từ một biểu thức wildcard.

## 12. QA sau weaving: bảo toàn hợp đồng

Bộ dệt có thể tạo bytecode hợp lệ nhưng advice vẫn làm sai chương trình. Với aspect chỉ quan sát, cần kiểm tra:

- **Return:** giá trị trả về và `void`/`null`/primitive không bị thay sai.
- **Throw:** lỗi nghiệp vụ gốc đi tới người gọi; logging/cleanup không vô tình che lỗi.
- **Count:** gọi tiếp một lần nếu không có retry; không nhân đôi side effect.
- **Order:** before/after/around, precedence và finally đúng.
- **Scope:** điểm mong muốn được áp, điểm ngoài phạm vi không bị áp.
- **Concurrency:** dữ liệu từng lần advice không bị lưu vào trạng thái dùng chung không an toàn.
- **Async:** phương thức trả future chưa chắc future đã hoàn tất.
- **Security:** những đường bắt buộc kiểm soát quyền không được bypass chỉ vì một class không được weave.

Đây là yêu cầu **chất lượng sản phẩm**, không chỉ kiểm tra cú pháp AOP.

## 13. Ma trận kiểm thử pipeline

| Tình huống | Điều cần chứng minh |
| --- | --- |
| Build sạch với aspect hợp lệ | Tạo woven output đúng |
| Build thiếu aspect bắt buộc | Bước kiểm chứng thất bại rõ ràng |
| Package sau weave | Artifact chứa bytecode mong muốn |
| Artifact cuối khi chạy | Advice được gọi tại điểm khớp |
| Method không khớp | Không chạy advice |
| Overload tương tự | Khớp chính xác theo chính sách |
| Trả về bình thường | Không đổi kết quả nếu chỉ theo dõi |
| Ném ngoại lệ | Không nuốt/che lỗi |
| Hai aspect cùng áp | Thứ tự đúng |
| Source không đổi, aspect đổi | Cache invalidation đúng |
| Weave hai lần ngoài ý muốn | Phát hiện hoặc ngăn cấu hình lỗi |
| Thiếu runtime dependency | Smoke test phát hiện lỗi |
| Thay toolchain/JDK | Kiểm tra tương thích bytecode |
| Lớp ngoài phạm vi weaving | Không tuyên bố đã được can thiệp |
| Giao dịch hoặc retry | Không tạo tác dụng phụ lặp ngoài hợp đồng |

## 14. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Tưởng có file aspect là đủ | Không có bytecode đã kết hợp | Gọi đúng compiler/weaver |
| Xem build success như advice success | Không biết advice chạy thật không | Test trên artifact cuối |
| Package original class thay vì woven | Chạy thiếu chính sách | Ràng buộc đường input/output |
| Unit test trước weaving thay integration test | Không kiểm tra advice | Thêm woven integration test |
| Cache không theo dõi aspect/config | Hành vi cũ sau khi sửa | Khai báo đủ task inputs |
| Weave lại output ngoài ý định | Có thể gây advice trùng | Kiểm soát một nguồn woven output |
| Quên thư viện runtime của advice | Lỗi nạp lớp/linkage | Rà runtime dependencies |
| Pointcut rộng theo tên | Khớp nhầm overload/phần nội bộ | Lọc chữ ký và phạm vi |
| Không xét thứ tự aspect | Đo/retry/transaction sai | Xác minh precedence |
| Đồng nhất CTW với proxy | Hiểu sai đường bypass | Phân biệt công nghệ và join point |
| Chỉ test đường thành công | Không thấy ngoại lệ bị che | Test throw, finally, retry |
| Dùng CTW cho chính sách bảo mật nhưng không đo coverage | Có thể bỏ sót đường truy cập | Kiểm tra điểm bắt buộc và đường đi vòng |

## 15. Checklist áp dụng vào một dự án

1. Xác định loại **join point** cần can thiệp và xác minh tool hỗ trợ.
2. Đặt **aspect, pointcut, advice** trong bộ input chính thức của task CTW.
3. Khóa phiên bản compiler/weaver, target JVM và dependency quan trọng.
4. Nêu rõ **phạm vi lớp được weave**, include/exclude và precedence.
5. Khai báo phụ thuộc build để output woven là điều kiện cho test/package.
6. Không trộn original và woven classes trong artifact.
7. Đảm bảo thay aspect/config làm build gia tăng cập nhật output.
8. Chạy test dương/âm, normal/throw, thứ tự và tác dụng phụ.
9. Chạy smoke test trên đúng JAR/image dự kiến triển khai.
10. Kiểm tra runtime library của bytecode đã weave.
11. Lưu định danh artifact và cấu hình build để tái lập/chẩn đoán.
12. Có cách triển khai/rollback phiên bản khi advice mới gây lỗi.

## 16. Bài tập tự kiểm tra

**Bài 1.** Một bộ dệt chạy lúc 10:00 trong CI, phương thức khớp pointcut chạy lúc 10:30. Khi nào weaving và advice xảy ra?

**Đáp án:** Weaving diễn ra lúc build 10:00; advice chạy lúc 10:30 khi join point xuất hiện và điều kiện được thỏa.

**Bài 2.** Compiler tạo `classes-original`, weaver tạo `classes-woven`, nhưng packaging lấy bản original. Vì sao không thấy advice?

**Đáp án:** Artifact triển khai không chứa output đã kết hợp. Cần ràng buộc task packaging lấy woven classes và test artifact cuối.

**Bài 3.** Mã nghiệp vụ giữ nguyên, pointcut được mở rộng; incremental build lại giữ output cũ. Nguyên nhân?

**Đáp án:** Bước weaving có thể thiếu định nghĩa aspect/config trong tập input dùng để invalidation cache. Phải khai báo đúng phụ thuộc.

**Bài 4.** Bộ test trên base class pass trước weaving. Có thể khẳng định advice không làm đổi ngoại lệ hay không?

**Đáp án:** Không. Cần test trên output đã weave, gồm đường trả về, ném lỗi và những điểm ngoài pointcut.

**Bài 5.** Vì sao method call join point trong mã `OrderService` không đồng nghĩa với method execution join point ở `PaymentService`?

**Đáp án:** Hai điểm ở hai vị trí/loại thao tác khác nhau. Weaver phải xử lý đúng mã chứa loại điểm mong muốn; chỉ tên phương thức không đủ.

**Bài 6.** Vì sao `Timer(Retry(Operation))` có thể cho kết quả khác `Retry(Timer(Operation))`?

**Đáp án:** Với Timer ngoài, có thể đo toàn chuỗi retry; với Timer trong, có thể đo mỗi attempt. Cần xác minh thứ tự aspect thực tế.

**Bài 7.** Một class đã weave, nhưng advice chưa chạy. Có phải build sai?

**Đáp án:** Chưa chắc. Có thể join point chưa được thực thi hoặc điều kiện runtime không thỏa. Cần test đúng đường gọi trước khi kết luận.

**Bài 8.** CTW có bảo đảm tự chặn mọi lệnh ghi field trực tiếp không?

**Đáp án:** Không. Khả năng ấy phụ thuộc mô hình field-set join point, phạm vi mã được xử lý và công cụ dệt thật.

## 17. Ghi nhớ

- **Compile-time weaving** kết hợp aspect khi tạo bytecode; **advice thực thi khi join point xảy ra ở runtime**.
- Đầu vào gồm **base code, aspect, pointcut/advice, thông tin kiểu, dependency, compiler/weaver và cấu hình**.
- Đầu ra là **woven class/artifact**, không nhất thiết sửa Java source.
- **Compile-time** khác **post-compile/binary**, **load-time** và **runtime proxy**; mỗi cơ chế có đầu vào, đầu ra và phạm vi riêng.
- Pipeline phải bảo đảm **đúng output woven được kiểm thử, đóng gói và triển khai**.
- Cache/incremental build phải phụ thuộc aspect/config, không chỉ mã nền; tránh double weaving và thiếu runtime dependency.
- Không công nhận AOP đã hoạt động đúng chỉ vì build xanh: cần xác minh **defined → selected → woven → executed**, gồm test dương/âm và bảo toàn hợp đồng nghiệp vụ.
