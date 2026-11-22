# Phân biệt lỗi biên dịch, lỗi dệt và lỗi thực thi trong kiến trúc AOP

> **Mục tiêu học tập:** Nhận diện ba nhóm sự cố quan trọng khi xây dựng chương trình có lập trình hướng khía cạnh (Aspect-Oriented Programming, AOP): **lỗi biên dịch** (*compilation errors*), **lỗi dệt** (*weaving errors*) và **lỗi thực thi** (*runtime errors*). Hiểu rằng dệt aspect có thể diễn ra ở nhiều thời điểm khác nhau; biết truy nguyên lỗi từ thông báo, giai đoạn pipeline, pointcut, advice, bytecode, class loader và đường thực thi; áp dụng quy trình chẩn đoán có bằng chứng thay vì suy đoán từ việc advice không chạy.

## 1. Tại sao chương trình AOP có thêm một lớp lỗi?

Trong chương trình Java thông thường, người học dễ phân biệt:

- **Biên dịch không thành công:** mã nguồn có lỗi cú pháp, kiểu dữ liệu, khai báo hoặc ràng buộc ngôn ngữ.
- **Chạy chương trình mới phát sinh lỗi:** chẳng hạn một lời gọi ném ngoại lệ hoặc thao tác với dữ liệu không hợp lệ.

Khi áp dụng AOP, còn có hoạt động **weaving**: kết hợp hành vi của aspect với chương trình ở những vị trí được mô hình join point và pointcut cho phép. Từ đây nảy sinh nhóm câu hỏi bổ sung:

- Pointcut có hợp lệ và đúng ngữ nghĩa không?
- Advice có thể được gắn vào loại join point yêu cầu không?
- Bộ dệt có đọc, phân tích và biến đổi được mã liên quan không?
- Những class nào thực sự nằm trong phạm vi weaving?
- Mã sau weaving còn thỏa hợp đồng bytecode/JVM không?
- Advice có thực sự chạy trên đường gọi đang quan sát không?

Một lỗi có thể xuất hiện **ngay khi build**, **khi xử lý bytecode**, **khi nạp class**, hoặc **sau khi chương trình đã chạy**. Điều quan trọng là không đồng nhất **giai đoạn phát hiện** với **bản chất nguyên nhân**.

Ví dụ: một cấu hình weaving sai có thể chỉ bị phát hiện ở thời điểm nạp class. Log xuất hiện trong lúc startup, nhưng nguyên nhân vẫn nằm ở **quy tắc dệt**, không nhất thiết ở logic của phương thức nghiệp vụ.

## 2. Ba nhóm lỗi dưới góc nhìn kiến trúc

| Nhóm | Bản chất chính | Triệu chứng thường gặp | Hướng điều tra đầu tiên |
|---|---|---|---|
| **Lỗi biên dịch** | Mã nguồn không được trình biên dịch chấp nhận theo ngôn ngữ và hệ kiểu | Báo cú pháp sai, không tìm thấy symbol, không tương thích kiểu | Tệp/dòng nguồn, compiler, classpath, phụ thuộc |
| **Lỗi dệt** | Không thể áp dụng hoặc xác nhận được phép kết hợp aspect với mã đích theo cơ chế weaving | Điểm dệt không hợp lệ, binding advice sai, biến đổi class thất bại, hạn chế model/weaver | Pointcut, advice binding, weaving scope, cấu hình và bytecode |
| **Lỗi thực thi** | Chương trình đã vào runtime nhưng luồng điều khiển/dữ liệu dẫn tới lỗi | Ngoại lệ nghiệp vụ, lỗi do advice, recursion, lỗi trạng thái, lỗi liên kết class | Stack trace, dữ liệu runtime, thứ tự advice, đường gọi |

Bảng giúp **phân loại nguyên nhân**, không phải cam kết luôn có ba công cụ hoặc ba pha hoàn toàn tách biệt.

### 2.1. Thời điểm phát hiện có thể trùng nhau

Một bộ dệt hoạt động **ngay trong quá trình biên dịch** có thể báo lỗi của chính hoạt động weaving trong cùng một lệnh build. Một bộ dệt lúc nạp class có thể báo lỗi khi ứng dụng đã khởi động. Do đó:

> **Lỗi dệt không có nghĩa lỗi chỉ xảy ra ở một thời điểm nằm giữa biên dịch và thực thi.**

Ngược lại, một lỗi `ClassNotFoundException` khi nạp class có thể do classpath/deployment sai, không phải do weaving. Cần căn cứ vào thông báo, stack trace, class đang được xử lý và giai đoạn thật sự phát sinh.

## 3. Pipeline khái niệm của một chương trình có AOP

Một cách mô hình hóa phổ biến:

~~~text
Mã nguồn ứng dụng + mã aspect
              |
              v
       Phân tích / biên dịch
              |
              v
        Mã trung gian / bytecode
              |
              v
       Tìm điểm dệt và áp dụng
              |
              v
          Mã đã được dệt
              |
              v
      Nạp class / xác minh / liên kết
              |
              v
        Chạy chương trình
              |
              v
   Advice, phần gốc, caller, I/O...
~~~

Sơ đồ chỉ mang tính **khái niệm**. Trong thực tế, thứ tự và ranh giới có thể thay đổi:

- Một số hệ AOP **dệt trong giai đoạn biên dịch**.
- Một số hệ AOP **dệt mã đã được biên dịch** sau đó.
- Một số hệ AOP **dệt lúc nạp class**.
- Một số cơ chế **chặn lời gọi bằng proxy/interceptor** tại runtime mà không biến đổi bytecode của phương thức gốc theo cùng cách.

Vì thế, việc phân loại lỗi cần gắn với **kiến trúc đang sử dụng**. Không nên buộc một mô hình proxy phải có cùng loại lỗi biến đổi bytecode như một bộ dệt mã.

## 4. Lỗi biên dịch: mã nguồn không hợp lệ

Lỗi biên dịch là lỗi xuất hiện khi trình biên dịch kiểm tra mã theo cú pháp, kiểu và các ràng buộc cần thiết.

Ví dụ mã Java **cố ý sai**, chỉ để minh họa lỗi kiểu:

~~~java
class CompileErrorExample {
    static int calculate() {
        return "not an integer";
    }
}
~~~

Đoạn trên **không biên dịch được** vì phương thức khai báo trả `int` nhưng biểu thức `return` là `String`. Khi chạy `javac CompileErrorExample.java`, trình biên dịch phải từ chối mã. Văn bản và vị trí của thông báo lỗi có thể khác tùy phiên bản và môi trường, nên không gán một stdout/stderr duy nhất như hợp đồng cố định.

**Đây là lỗi Java**, ngay cả khi lớp nằm trong ứng dụng có dùng AOP. Không nên vội điều tra pointcut khi một dòng `return` sai kiểu ngay trong source đã giải thích thất bại.

### 4.1. Những lỗi biên dịch quen thuộc

- Cú pháp không đúng, thiếu dấu hoặc khai báo không hợp lệ.
- Không tìm thấy một lớp, interface, method hoặc biến được sử dụng.
- Kiểu tham số và kiểu trả về không tương thích.
- Mâu thuẫn trong overload, generic hoặc modifier theo quy tắc Java.
- Không tuân thủ quyền truy cập mà compiler kiểm tra.
- Thư viện cung cấp API aspect không nằm đúng trên classpath/module path.
- Mã advice viết bằng Java nhưng khai báo tham số hoặc return không thỏa hợp đồng biên dịch.

### 4.2. Không phải mọi lỗi cú pháp pointcut đều chỉ là lỗi Java

Nếu một mô hình AOP có **ngôn ngữ biểu thức pointcut riêng**, biểu thức sai có thể bị báo bởi bộ phân tích pointcut, trình biên dịch mở rộng hoặc bộ dệt. Nguồn thất bại thuộc **khâu xử lý quy tắc AOP**, dù thông báo được in trong một lệnh có tên “compile”.

Cần xem lớp thành phần nào phát hiện lỗi:

~~~text
Java parser / type checker?
Pointcut parser / validator?
Advice binding checker?
Weaving engine?
JVM verifier / linker?
Application code?
~~~

Đây là cách phân loại hữu ích hơn việc chỉ nhìn tên tiến trình đã dừng.

## 5. Lỗi dệt: không thể kết hợp aspect với vị trí cần can thiệp

**Weaving error** chỉ vấn đề khi phân tích, lựa chọn, gắn hoặc biến đổi mã nhằm thực thi advice ở một join point được hỗ trợ.

Những nguyên nhân có thể xảy ra:

1. **Biểu thức pointcut không hợp lệ** theo cú pháp/đặc tả công cụ.
2. **Ràng buộc tham số advice không khớp** với dữ liệu mà join point có thể cung cấp.
3. **Loại join point không được hỗ trợ** bởi mô hình hoặc một dạng around advice cụ thể.
4. **Không thể đọc, biến đổi hoặc ghi class** thuộc phạm vi dệt.
5. **Phiên bản bytecode hoặc môi trường JVM không tương thích** với công cụ weaving.
6. **Lớp đã được nạp**, và cơ chế hiện tại không cho áp dụng thay đổi theo cách yêu cầu.
7. **Quy tắc weaving xung đột** hoặc vi phạm một ràng buộc do bộ dệt áp đặt.
8. **Class loader/module/access boundary** khiến quá trình kết hợp mã thất bại.
9. **Bytecode được tạo ra không hợp lệ** và bị bộ kiểm tra JVM từ chối, nếu lỗi thực sự bắt nguồn từ mã đã được biến đổi.

Không phải công cụ nào cũng có mọi nguyên nhân trên. Một số lỗi được báo là **warning**, một số là **error**, và có vấn đề chỉ xuất hiện ở runtime.

### 5.1. Pointcut hợp lệ nhưng không khớp không nhất thiết là lỗi dệt

Nếu pointcut chọn `submit*` nhưng chương trình chỉ có `cancelOrder()`, tập khớp có thể rỗng và bộ dệt vẫn hoàn tất thành công.

~~~text
Pointcut hợp lệ + không có join point khớp
    ≠
Pointcut lỗi cú pháp
    ≠
Weaving engine thất bại
~~~

Một pointcut không khớp thường là **vấn đề độ bao phủ hoặc cấu hình**, không tự là ngoại lệ bắt buộc của bộ dệt. Công cụ có thể phát cảnh báo hoặc coi là lỗi tùy chính sách cấu hình, nhưng không được tự gán kết luận.

## 6. Sai cú pháp pointcut so với sai ngữ nghĩa lựa chọn

Xét hai tình huống khái niệm:

**Tình huống A — sai cú pháp:**

~~~text
select method-execution(  // thiếu cấu trúc bắt buộc
~~~

Một parser phù hợp phải từ chối biểu thức theo ngữ pháp của chính công cụ.

**Tình huống B — cú pháp đúng, chọn sai phạm vi:**

~~~text
select executions named "save*"
~~~

Nếu ý định là chọn `submit*`, nhưng quy tắc lại chọn `save*`, biểu thức có thể hợp lệ hoàn toàn. Bộ dệt vẫn chạy; advice chỉ xuất hiện **không đúng chỗ** hoặc **không xuất hiện**.

Bài học:

- **Syntax error:** câu viết không thuộc ngôn ngữ biểu thức hợp lệ.
- **Semantic/configuration mismatch:** câu viết được chấp nhận nhưng diễn đạt sai ý định.
- **Coverage failure:** cơ chế không can thiệp vào đường chạy mong muốn.

Ba vấn đề này có thể có biểu hiện tương tự “không thấy advice”, nhưng cách khắc phục khác.

## 7. Binding của advice có thể không tương thích join point

Một advice có thể cần nhận:

- Đối số của lời gọi.
- Đối tượng đích hoặc receiver.
- Chữ ký của điểm can thiệp.
- Kết quả trả về.
- Ngoại lệ đi ra khỏi một ranh giới.

Nhưng dữ liệu nào có thể bind tùy loại join point và loại advice. Ví dụ:

- Advice chạy **trước** không thể giả định đã có return value của lần thực thi chưa xảy ra.
- Một constructor không có kiểu trả về thông thường như method Java.
- Một field get/set join point (nếu có) không có cùng danh sách tham số như method execution.
- Binding dữ liệu theo tên tham số có thể chịu giới hạn metadata và ngôn ngữ pointcut.

Nếu công cụ kiểm tra được binding lúc dệt, nó có thể từ chối một advice đòi dữ liệu không tồn tại hoặc kiểu không hợp lệ.

**Không được kết luận mọi mismatch sẽ được phát hiện trước runtime.** Một số lỗi chỉ được kiểm tra khi một pointcut động khớp hoặc khi adapter nhận dữ liệu thực tế.

## 8. Không hỗ trợ loại join point khác với không khớp điều kiện

Đây là một phân biệt kiến trúc quan trọng.

**Trường hợp 1 — không hỗ trợ:** Cơ chế chỉ quan sát lời gọi method qua proxy, nhưng yêu cầu là chặn **gán trường trực tiếp**.

**Trường hợp 2 — không khớp:** Mô hình có hỗ trợ method execution, nhưng pointcut chỉ chọn tên `save`, còn phương thức thực tế là `send`.

**Trường hợp 3 — không được dệt:** Công cụ có khả năng xử lý method execution và pointcut đúng, nhưng lớp đích bị loại khỏi weaving scope.

| Trường hợp | Lỗi cốt lõi | Điều cần làm |
|---|---|---|
| Loại join point chưa được hỗ trợ | Giới hạn mô hình | Đổi ranh giới can thiệp hoặc cơ chế phù hợp |
| Điểm được hỗ trợ nhưng không khớp | Điều kiện pointcut | Sửa biểu thức lựa chọn, kiểm tra ca dương/âm |
| Điểm khớp nhưng mã chưa được dệt | Weaving scope/cấu hình | Xác minh danh sách class, class loader, thứ tự xử lý |
| Điểm được dệt nhưng chưa xảy ra | Luồng thực thi | Kích hoạt đúng ca chạy, kiểm tra điều kiện động |
| Advice đã chạy và ném lỗi | Hành vi runtime | Đọc stack trace, xử lý return/throw và thứ tự advice |

Đừng lấy việc “không có log” làm bằng chứng bộ dệt thất bại. Đầu tiên phải chứng minh có một **sự kiện phù hợp** xảy ra trên **đường đã được can thiệp**.

## 9. Compile-time weaving: lỗi dệt xuất hiện ngay lúc build

Với **compile-time weaving**, quá trình xử lý aspect có thể diễn ra cùng giai đoạn biên dịch source. Một lệnh build có thể vừa:

1. Phân tích cú pháp và kiểm tra kiểu của source.
2. Phân tích pointcut và advice.
3. Xác định những vị trí thích hợp để kết hợp mã.
4. Sinh bytecode đã được dệt.

Nếu bước 1 lỗi, có thể là lỗi biên dịch Java. Nếu bước 2/3/4 lỗi, nguyên nhân có thể là **weaving**, nhưng vẫn nằm trong **cùng phiên build**.

### 9.1. Hậu quả với cách đọc log

Khi một lệnh build báo “failed”, hãy kiểm tra:

- Thông báo chỉ ra lỗi ở **source Java** hay biểu thức pointcut?
- Stack trace bắt đầu ở **compiler** hay **weaving component**?
- Vấn đề liên quan một class cụ thể đang được biến đổi?
- Có báo “không thể áp dụng advice”, “binding mismatch”, “không hỗ trợ version” hay không?
- Có nhiều lỗi: lỗi đầu tiên khiến các lỗi tiếp theo chỉ là hậu quả dây chuyền?

Chỉ sau khi xác định giai đoạn gây lỗi mới chọn đúng hướng sửa.

## 10. Post-compile / binary weaving: mã đã biên dịch nhưng chưa dệt được

Một số kiến trúc dệt **bytecode đầu vào đã được biên dịch**. Khi đó:

~~~text
Source Java hợp lệ
        |
        v
    .class ban đầu
        |
        v
   Binary weaving
        |
        v
   .class được dệt
~~~

Một dự án có thể `javac` thành công nhưng bước dệt binary thất bại vì:

- Class file có cấu trúc/phiên bản không tương thích với bộ dệt.
- Một thư viện phụ thuộc hoặc class metadata cần để phân tích chưa có.
- Quá trình ghi output bị hạn chế quyền hoặc cấu hình sai.
- Một quy tắc aspect không áp dụng hợp lệ lên bytecode được chọn.
- Bộ dệt gặp trường hợp mã sinh hoặc tổ hợp class chưa được hỗ trợ.

**Không nên sửa source Java chỉ vì bước sau biên dịch báo lỗi** nếu log đã chỉ ra lỗi nằm ở compatibility hoặc cấu hình dệt. Cần cô lập input/output của bộ dệt và xác minh chính xác class bị ảnh hưởng.

### 10.1. Hỏi bộ dệt đã xử lý mã nào?

Có ba trạng thái khác nhau:

~~~text
Không tìm thấy class cần xử lý
Tìm thấy class nhưng không có join point match
Tìm thấy class và match, nhưng dệt thất bại
~~~

Chúng không thể được xử lý bằng cùng một cách. Một tình huống không match có thể hoàn toàn hợp lệ, còn tình huống thứ ba là thất bại kỹ thuật thực sự.

## 11. Load-time weaving: lỗi dệt có thể xuất hiện khi chương trình khởi động

Với **load-time weaving**, bộ dệt xử lý class khi nó đang được nạp hoặc khi một cơ chế instrumentation phù hợp can thiệp vào quá trình tải class.

Có thể mô tả:

~~~text
Application starts
      |
      v
Class loader requests Class X
      |
      v
Weaving / transform hook
      |
      v
Class verifier and linker
      |
      v
Class usable by runtime
~~~

Vì vậy, stack trace ở startup có thể chứa lỗi từ bộ dệt. Không có lý do để gọi mọi lỗi trong startup là “lỗi logic runtime của business”.

### 11.1. Cấu hình nạp lớp

Các vấn đề thường cần kiểm tra:

- Cơ chế weaving đã được kích hoạt đúng cách chưa?
- Class có được nạp bởi class loader nằm trong phạm vi dự kiến không?
- Class có bị nạp **trước** khi cơ chế weaving có hiệu lực không?
- Những class/library có thể bị loại khỏi vùng dệt không?
- Cơ chế có hỗ trợ class file version mà compiler đang phát sinh không?
- Có nhiều phiên bản của cùng loại runtime/API AOP trên classpath không?
- JVM có cho phép biến đổi class ở giai đoạn được yêu cầu không?

Một ứng dụng có thể hoạt động với lời gọi thông thường nhưng **không có advice** nếu những class quan trọng không đi qua cơ chế dệt. Đó có thể là **mismatch về phạm vi** thay vì lỗi có exception rõ ràng.

### 11.2. Khi nào cần quan tâm việc class đã nạp?

Một số kỹ thuật có thể biến đổi class ở thời điểm nạp nhưng không tự hỗ trợ mọi trường hợp **retransform** hoặc thay đổi cấu trúc sau khi class đã được định nghĩa. Cần kiểm tra điều kiện thực tế của công cụ, không giả định bật cấu hình vào bất kỳ lúc nào cũng dệt lại mã đã nạp.

## 12. JVM verification, linkage và lỗi “nằm ở ranh giới”

Sau khi mã được dệt, JVM còn có các giai đoạn xác minh và liên kết. Những lỗi như **VerifyError**, **ClassFormatError**, **NoClassDefFoundError**, **NoSuchMethodError** hoặc **IllegalAccessError** có thể xuất hiện ở những tình huống khác nhau.

**Không phải cứ gặp các tên lỗi đó là lỗi dệt.** Cần xem nguyên nhân:

| Hiện tượng | Những khả năng phải phân biệt |
|---|---|
| `VerifyError` | Bytecode không thỏa quy tắc xác minh; có thể do biến đổi không hợp lệ, cũng có thể do input/công cụ khác |
| `ClassFormatError` | Cấu trúc class file không hợp lệ; xác định class gốc hay class sau biến đổi |
| `NoClassDefFoundError` | Class cần thiết không có ở thời điểm liên kết/thực thi hoặc khởi tạo class trước đó thất bại |
| `NoSuchMethodError` | Mã biên dịch tham chiếu một method không có trong phiên bản class thực tế; thường liên quan mismatch nhị phân |
| `IllegalAccessError` | Vi phạm điều kiện truy cập trong quá trình liên kết/thực thi |
| `ExceptionInInitializerError` | Khởi tạo class bằng static initializer thất bại; có thể là lỗi logic hoặc tương tác với mã dệt |

Nếu bytecode nguyên gốc chạy hợp lệ nhưng cùng input sau weaving gây `VerifyError`, chứng cứ hướng tới **vấn đề biến đổi / tương thích bytecode**. Tuy nhiên muốn kết luận cần kiểm tra thật sự hai artifact tương ứng và tránh nhầm classpath.

## 13. Lỗi thực thi: khi chương trình đã vào luồng xử lý

Sau khi phần cần thiết được biên dịch, dệt và nạp thành công, chương trình vẫn có thể gặp lỗi:

- `NullPointerException`, `IllegalArgumentException` hoặc lỗi nghiệp vụ.
- Advice đọc đối số theo vị trí sai hoặc ép kiểu sai.
- Advice thiếu kiểm tra `null` đối với target hoặc argument.
- Around advice **quên gọi continuation/proceed**, khiến nghiệp vụ bị bỏ qua.
- Around advice **gọi proceed nhiều lần**, tạo tác dụng phụ lặp khi cơ chế cho phép.
- Advice ghi log hoặc serialize object rồi tự ném lỗi.
- Advice thay return value không tương thích hoặc che mất ngoại lệ gốc.
- Các advice lồng nhau tương tác sai về thứ tự, ngữ cảnh hoặc trạng thái.
- Một lời gọi bị tái chặn gây đệ quy và cạn stack.
- Cạnh tranh dữ liệu hoặc rò trạng thái khi chạy đồng thời.

Đây là các ví dụ về **hành vi runtime**, nhưng nguồn gây lỗi có thể nằm trong advice hoặc trong nghiệp vụ gốc. Vì vậy cần phân biệt **“ngoại lệ của ứng dụng có AOP”** với **“ngoại lệ do chính aspect gây ra”**.

### 13.1. Runtime exception không đồng nghĩa lỗi dệt

Nếu aspect đã được dệt chính xác và advice dùng `args[2]` trong khi chỉ có hai đối số, `ArrayIndexOutOfBoundsException` phát sinh là lỗi của **logic advice lúc chạy**.

Bộ dệt có thể hoàn toàn đúng khi đưa advice vào join point. Không nên “sửa cấu hình weaving” trước khi kiểm tra phép truy cập mảng.

## 14. Thứ tự thời điểm: lỗi ở phần gốc và lỗi ở advice

Xét chuỗi:

~~~text
Caller
  |
  v
Around advice A
  |
  v
Before advice B
  |
  v
Original method
  |
  v
After/finally advice C
  |
  v
Caller
~~~

Lỗi có thể xảy ra ở nhiều nơi:

1. **A ném trước proceed:** B và phần gốc có thể chưa chạy.
2. **B ném trước phần gốc:** phương thức nghiệp vụ có thể chưa được gọi.
3. **Phần gốc ném lỗi:** lỗi có thể được C/A quan sát nếu semantics và cấu trúc bao cho phép.
4. **C ném trong cleanup:** lỗi mới có thể che mất lỗi từ phần gốc.
5. **A bắt rồi chuyển lỗi:** caller có thể thấy lỗi đã được chuyển dạng, không phải exception ban đầu.

Không có một thứ tự advice chung áp dụng cho mọi cơ chế; ví dụ trên minh họa một **chuỗi giả định đã được sắp xếp**.

### 14.1. Dấu hiệu trong stack trace

Nếu stack trace có lớp trung gian/proxy hoặc mã đã dệt, không có nghĩa thành phần đó là nguyên nhân. Nó có thể chỉ là **khung bao** mà ngoại lệ nghiệp vụ đi xuyên qua.

Cần tìm **điểm tạo lỗi đầu tiên có ý nghĩa**, thông điệp và chuỗi `cause` hoặc `suppressed`; không chỉ chọn khung đầu tiên có tên “interceptor”.

## 15. Ví dụ Java 17 hoàn chỉnh: mô phỏng lỗi cấu hình can thiệp và lỗi runtime

Ví dụ dưới đây tạo một mô hình **đơn giản, tự chứa** để quan sát khác biệt:

- **Kiểm tra kế hoạch can thiệp trước khi tạo proxy**: một mô phỏng lỗi ở bước chuẩn bị/dệt khi yêu cầu một method không có.
- **Tạo proxy hợp lệ**: phương thức mục tiêu tồn tại và adapter hoạt động.
- **Nghiệp vụ ném lỗi tại runtime**: một lời gọi có `amount` âm gây lỗi.
- **Đường gọi trực tiếp không qua proxy**: nghiệp vụ vẫn chạy, nhưng không in dòng intercept.

**Chú ý:** Java Dynamic Proxy trong ví dụ **không thực hiện bytecode weaving**. Hàm `validatePlan` chỉ mô phỏng việc kiểm tra một kế hoạch dệt để dạy cách phân loại lỗi. Không gọi kết quả này là lỗi của một bộ dệt AOP cụ thể.

Lưu file **`WeavingDiagnosticsDemo.java`**:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public class WeavingDiagnosticsDemo {
    public interface Billing {
        String charge(int amount);
    }

    static final class BillingImpl implements Billing {
        @Override
        public String charge(int amount) {
            if (amount < 0) {
                throw new IllegalArgumentException("negative amount");
            }
            return "OK:" + amount;
        }
    }

    record ObservationPlan(String methodName, int parameterCount) {}

    static void validatePlan(Class<?> contract, ObservationPlan plan) {
        if (!contract.isInterface()) {
            throw new IllegalArgumentException("contract must be interface");
        }
        boolean found = false;
        for (Method method : contract.getMethods()) {
            if (method.getName().equals(plan.methodName())
                    && method.getParameterCount() == plan.parameterCount()) {
                found = true;
                break;
            }
        }
        if (!found) {
            throw new IllegalArgumentException(
                    "no matching method: " + plan.methodName()
                    + "/" + plan.parameterCount());
        }
    }

    static Billing wrap(Billing target, ObservationPlan plan) {
        validatePlan(Billing.class, plan);
        return (Billing) Proxy.newProxyInstance(
                Billing.class.getClassLoader(),
                new Class<?>[] {Billing.class},
                (proxy, method, args) -> {
                    System.out.println("[intercept] " + method.getName());
                    try {
                        return method.invoke(target, args);
                    } catch (InvocationTargetException wrapped) {
                        throw wrapped.getCause();
                    }
                }
        );
    }

    public static void main(String[] args) {
        System.out.println("phase: configuration");

        try {
            validatePlan(
                    Billing.class, new ObservationPlan("refund", 1));
        } catch (IllegalArgumentException error) {
            System.out.println("[plan-error] " + error.getMessage());
        }

        Billing target = new BillingImpl();
        Billing observed = wrap(
                target, new ObservationPlan("charge", 1));

        System.out.println("[setup] ok");
        System.out.println("[success] " + observed.charge(12));

        try {
            observed.charge(-1);
        } catch (IllegalArgumentException error) {
            System.out.println("[runtime-error] " + error.getMessage());
        }

        System.out.println("[direct] " + target.charge(4));
    }
}
~~~

Biên dịch và chạy trên JDK 17 hoặc mới hơn:

~~~bash
javac WeavingDiagnosticsDemo.java
java WeavingDiagnosticsDemo
~~~

**Stdout chính xác:**

~~~text
phase: configuration
[plan-error] no matching method: refund/1
[setup] ok
[intercept] charge
[success] OK:12
[intercept] charge
[runtime-error] negative amount
[direct] OK:4
~~~

### 15.1. Tại sao đây không phải minh họa một lỗi biên dịch thật?

Tệp Java hợp lệ nên `javac` có thể tạo class thành công. Kế hoạch sai `refund/1` chỉ được chương trình kiểm tra **khi chạy `main`**. Nó mô phỏng một phép kiểm tra ở **giai đoạn chuẩn bị cơ chế can thiệp**, không phải một compiler error và cũng không phải lỗi dệt bytecode thật.

Nếu một công cụ AOP có phân tích binding/pointcut ở compile-time thì chính sách tương ứng có thể bị bác bỏ sớm hơn. Cách thực hiện cụ thể tùy công cụ.

### 15.2. Phân biệt plan-error và runtime-error

`[plan-error] no matching method: refund/1` nghĩa là **yêu cầu chuẩn bị điểm can thiệp** không tìm thấy phương thức tương ứng theo quy tắc đơn giản trong demo.

`[runtime-error] negative amount` nghĩa là **nghiệp vụ `charge` đã được gọi** với dữ liệu không hợp lệ và tự ném `IllegalArgumentException`.

Hai dòng có thể cùng xuất hiện trong một lần chạy nhưng nằm ở **hai loại nguyên nhân khác nhau**. Không nên sửa pointcut khi lỗi thực tế là `amount < 0`.

### 15.3. Vì sao cần xử lý `InvocationTargetException`?

`Method.invoke` dùng reflection có thể bọc ngoại lệ của method đích trong `InvocationTargetException`. Handler giải lớp bọc và ném lại `wrapped.getCause()`.

Điều này giúp caller nhận `IllegalArgumentException("negative amount")` trong ví dụ. Nếu không giải bọc đúng, hiện tượng runtime có thể bị biến dạng thành lỗi reflection/proxy. Đây là đặc điểm của **adapter dùng reflection**, không phải mọi weaving engine đều xử lý ngoại lệ giống cách này.

### 15.4. Trường hợp direct cho thấy điều gì?

`target.charge(4)` trả `OK:4` mà không có dòng `[intercept]`. Nguyên nhân là đường gọi **không đi qua proxy**.

Đây **không phải lỗi biên dịch**, **không phải lỗi của bộ dệt bytecode**, và **không phải bằng chứng method không được chạy**. Nó là sự khác biệt giữa **đường đi qua cơ chế chặn** và **đường gọi trực tiếp**.

Nếu một chương trình yêu cầu mọi lời gọi đều được ghi, phải kiểm tra kiến trúc điểm can thiệp, không chỉ tìm exception.

## 16. Lỗi không xuất hiện dưới dạng exception: “advice biến mất”

Một trong những trường hợp khó nhất là chương trình **vẫn chạy và trả kết quả đúng** nhưng advice không xuất hiện như dự kiến.

Có ít nhất sáu khả năng:

1. Pointcut hợp lệ nhưng không khớp với tên/chữ ký.
2. Điều kiện động không đúng ở lần gọi.
3. Loại join point cần quan sát không nằm trong mô hình công cụ.
4. Class nằm ngoài vùng weaving hoặc được nạp qua đường khác.
5. Caller đi thẳng tới target thay vì proxy/interceptor.
6. Nhánh mã có join point chưa từng được thực thi trong ca thử.

Ngoài ra, còn có thể có vấn đề ở **kênh log**: advice đã chạy nhưng mức log bị lọc, sink không ghi, dữ liệu bị drop hoặc sự kiện ghi không đúng nhãn.

Vì vậy, “không thấy log” chỉ là **triệu chứng**. Hãy thiết kế một advice/điểm kiểm thử có thể quan sát bằng bộ đếm hoặc sự kiện độc lập, đồng thời kiểm tra trực tiếp phần gốc có được gọi hay không.

## 17. Quy trình điều tra khi advice không chạy

Thực hiện từ đơn giản đến phức tạp:

1. **Xác nhận code path:** dòng nghiệp vụ dự kiến có thật sự được chạy?
2. **Xác nhận loại join point:** điểm đang cần chặn là method call, execution, constructor, field access hay sự kiện khác?
3. **Kiểm tra support:** cơ chế hiện tại có hỗ trợ loại điểm ấy không?
4. **Kiểm tra pointcut:** tên, chữ ký, metadata, điều kiện AND/OR/NOT có đúng không?
5. **Kiểm tra điều kiện động:** giá trị đối số/receiver/cflow có khớp lần chạy này không?
6. **Kiểm tra weaving scope:** class/package/module có nằm trong vùng xử lý?
7. **Kiểm tra class loading:** class đã được nạp trước lúc dệt chưa; runtime có đúng cấu hình?
8. **Kiểm tra runtime path:** lời gọi có đi qua proxy/adapter nếu cơ chế yêu cầu?
9. **Kiểm tra advice:** có thực thi nhưng log bị lọc hoặc bị lỗi trước khi in không?
10. **Kiểm tra sự phối hợp:** advice bao ngoài có short-circuit khiến advice phía trong không chạy không?

Không nên thay đồng thời pointcut, class loader, thứ tự advice và logic nghiệp vụ; như vậy sẽ đánh mất khả năng xác định **thay đổi nào giải quyết vấn đề**.

## 18. Quy trình điều tra lỗi dệt có thông báo rõ ràng

Khi công cụ báo không thể weave, hãy giữ nguyên văn những thông tin sau:

- **Văn bản lỗi và mã lỗi**, nếu có.
- **Giai đoạn**: compile-time, binary weaving hay load-time.
- **Class hoặc vị trí mã** đang được xử lý.
- **Pointcut/advice** được cho là liên quan.
- **Compiler, JVM, weaving runtime** và phiên bản phù hợp.
- **Classpath/module path/class loader** có liên quan.
- **Nguyên nhân gốc** trong chuỗi cause, không chỉ thông báo cấp cao.
- **Artifact đầu vào và đầu ra** nếu có thể giữ an toàn để đối chiếu.

Sau đó phân nhóm:

~~~text
Ngôn ngữ / cú pháp?
Binding / loại join point?
Khả năng hỗ trợ / phiên bản bytecode?
Phạm vi weaving / loading?
Tạo bytecode / verification / linkage?
Lỗi riêng của mã nghiệp vụ sau khi advice chạy?
~~~

Nếu có lỗi verification của class đã được xử lý, cần kiểm tra cả **artifact trước** và **sau weaving**, cùng JVM/tool versions. Không tự sửa logic nghiệp vụ khi chưa chứng minh code nghiệp vụ là nguồn lỗi.

## 19. Chẩn đoán với công cụ Java phổ biến

Các công cụ Java có thể giúp phân tách nguồn lỗi dù không phụ thuộc một framework AOP.

### 19.1. Kiểm tra compile Java

~~~bash
javac -Xlint:all WeavingDiagnosticsDemo.java
~~~

Lệnh trên yêu cầu `javac` hiển thị cảnh báo bổ sung mà compiler hỗ trợ, không biến compiler Java chuẩn thành một engine weaving AOP. Một file compile được không chứng minh pointcut, aspect hay cấu hình dệt đều đúng.

### 19.2. Xem bytecode

~~~bash
javap -c -p WeavingDiagnosticsDemo
~~~

`javap` giúp xem bytecode của class có thể truy cập được. Nếu có artifact **trước và sau weaving** dưới dạng riêng biệt, việc so sánh bytecode có thể hỗ trợ xác định mã dệt đã được áp dụng. Không có thay đổi trong một class cụ thể chưa tự chứng minh toàn bộ hệ thống không được weaving; có thể điểm can thiệp nằm ở class/call site khác.

### 19.3. Theo dõi class loading trên JDK hiện đại

~~~bash
java -Xlog:class+load=info WeavingDiagnosticsDemo
~~~

Lệnh minh họa yêu cầu JVM ghi thêm thông tin class loading. Output có thể rất dài và phụ thuộc môi trường; vì vậy **không đưa stdout cố định** cho lệnh này. Log tải class giúp tìm tên/nguồn của class được nạp, nhưng không tự cho biết pointcut có match hay advice có chạy hay không.

### 19.4. Kiểm tra JVM verification

Một số tình huống có thể thử:

~~~bash
java -Xverify:all WeavingDiagnosticsDemo
~~~

Lệnh yêu cầu JVM xác minh bytecode theo chế độ được hỗ trợ. Nó có thể giúp phát hiện một số lỗi class file; không bảo đảm chứng minh toàn bộ ngữ nghĩa AOP đúng.

**Nguyên tắc:** dùng công cụ để **thu thập bằng chứng theo giả thuyết**, không chạy hàng loạt tùy chọn rồi gắn nhãn lỗi theo dòng log xuất hiện đầu tiên.

## 20. Cẩn thận với lỗi classpath và binary compatibility

Một hệ thống có thể:

1. Biên dịch với phiên bản thư viện A.
2. Dệt với metadata/phiên bản B.
3. Chạy với phiên bản C.

Nếu các phiên bản không tương thích, lỗi có thể xuất hiện dưới dạng **linkage error** khi nạp hoặc gọi method.

Một `NoSuchMethodError` có thể bắt nguồn từ việc class thực tế ở runtime **không còn method** mà bytecode đang tham chiếu. Có thể do thư viện bị thay, khác nhánh build, class loader lấy sai bản hoặc quá trình tạo mã. **Không có lý do để tự kết luận lỗi pointcut** chỉ vì dự án có dùng AOP.

Một quy trình xác minh hữu ích:

- Cùng một bộ artifact đã build có được dùng khi weave và run không?
- Có jar/class trùng tên trên classpath hoặc module path không?
- Compiler và runtime dùng JDK tương thích không?
- Nếu có mã sinh/dệt, output cuối có được đóng gói và triển khai đúng bản?
- Lỗi bắt đầu trước hay sau lúc class được tải/định nghĩa?

## 21. Khi nào runtime error thật sự do advice?

Một số dấu hiệu thường gặp:

### 21.1. Kiểu đối số không như giả định

Advice đọc đối số thứ hai rồi ép sang `String`, nhưng thực tế là `Integer`: xảy ra `ClassCastException` nếu code không kiểm tra kiểu.

**Khắc phục:** binding theo descriptor rõ, kiểm tra kiểu, không suy từ tên method.

### 21.2. `null` hoặc object lifecycle

Advice đọc `this` hoặc target ngay tại giai đoạn khởi tạo mà đối tượng chưa có trạng thái mong đợi: có thể xuất hiện NPE hoặc phá bất biến.

**Khắc phục:** xác định loại join point và thời điểm quan sát chính xác.

### 21.3. Advice gọi lại chính điểm đang bị chặn

Một advice gọi trực tiếp một method qua cùng ranh giới interceptor, dẫn tới vòng lặp advice → method → advice → method.

**Khắc phục:** dùng continuation/`proceed` đúng hợp đồng; phân biệt lời gọi mới với tiếp tục join point hiện tại.

### 21.4. Advice tự ném lỗi khi logging

Serialization hoặc `toString()` trên đối số ném lỗi, khiến caller nhận lỗi quan sát thay vì kết quả gốc.

**Khắc phục:** log tối thiểu, masking, chính sách lỗi rõ, kiểm thử exception path.

### 21.5. Quên proceed hoặc gọi nhiều lần

Một around advice trả giá trị thay thế mà không tiếp tục, hoặc retry không kiểm soát, làm mất/thêm tác dụng phụ.

**Khắc phục:** kiểm tra số lần phần gốc chạy và tính idempotent, không chỉ dựa vào số lần advice chạy.

### 21.6. Lỗi thứ tự khi nhiều advice kết hợp

Một advice thiết lập context trong before, advice khác đọc context khi context chưa được thiết lập hoặc đã bị cleanup.

**Khắc phục:** mô tả lớp ngoài/lớp trong, kiểm chứng thứ tự có thực, dùng cấu trúc lưu/phục hồi an toàn.

## 22. Một chương trình compile thành công nhưng không có advice: có phải lỗi runtime?

Không nhất thiết. Hãy phân biệt:

~~~text
Trạng thái A: chương trình compile được, pointcut không match.
Trạng thái B: pointcut match, nhưng vùng class không được weave.
Trạng thái C: đã weave, nhưng code path chưa chạy.
Trạng thái D: điểm đã chạy, advice đã chạy, nhưng sink không ghi log.
Trạng thái E: advice chạy và ném lỗi.
~~~

Chỉ trạng thái E chắc chắn có **lỗi runtime ở advice**. Trạng thái A/B thường là vấn đề cấu hình/lựa chọn/bao phủ. Trạng thái C có thể là hành vi bình thường. Trạng thái D là vấn đề observability.

Vì vậy nhãn chẩn đoán không chỉ là “compile/weave/runtime” mà còn cần nêu **đã xảy ra điều gì** và **điểm can thiệp nào**.

## 23. Lưu ý về cảnh báo (warning) và lỗi nghiêm trọng (error)

Một số bộ phân tích pointcut có thể báo:

- Không tìm thấy điểm khớp cho mẫu quá hẹp.
- Một điều kiện cấu trúc không thể khớp với loại phần tử nào đó.
- Một giới hạn công cụ hoặc một khả năng không được hỗ trợ.
- Một lời cảnh báo về kiểu, metadata hoặc hành vi có khả năng không an toàn.

Không phải warning nào cũng làm build thất bại. Một hệ CI có thể cấu hình **warnings as errors**, biến cảnh báo thành nguyên nhân dừng pipeline.

Khi gặp một dòng cảnh báo, nên xác minh:

1. Nó biểu thị điều kiện **chắc chắn sai**, khả năng sai hay chỉ thông tin?
2. Cấu hình hiện tại có yêu cầu build phải dừng không?
3. Điểm bị cảnh báo có thật sự nằm trong yêu cầu độ bao phủ hay không?
4. Một warning không match được xem là lỗi bởi **chính sách dự án**, hay bởi đặc tả công cụ?

Không tùy tiện tắt cảnh báo để pipeline xanh nếu nó báo rằng chính sách kiểm soát quan trọng không được gắn.

## 24. Không phải mọi công cụ AOP đều biến đổi bytecode

Một cơ chế dựa trên **proxy/interceptor** có thể thiết lập đối tượng trung gian rồi chặn các lời gọi đi qua nó mà không nhất thiết biến đổi class đích như một bộ dệt bytecode truyền thống.

Do đó, trong một kiến trúc proxy:

- Lỗi tạo proxy hoặc cấu hình interceptor tương ứng với **lỗi thiết lập cơ chế can thiệp**.
- Lời gọi không đi qua proxy là **giới hạn đường gọi**, không tự là lỗi weaving bytecode.
- Lỗi trong handler tại runtime là **lỗi logic/interceptor**.
- Class không có interface hoặc phương thức không được đường proxy hỗ trợ có thể là **giới hạn thiết kế**, không phải một lỗi cú pháp pointcut.

Nên sử dụng khái niệm **lỗi dệt** cho hệ có weaving theo nghĩa rõ ràng. Khi giải thích rộng cho nhiều mô hình, có thể nói **lỗi cấu hình/thiết lập can thiệp** để tránh gán nhãn bytecode weaving sai cho proxy.

## 25. Kiểm thử theo ba tầng để xác định sớm lỗi

### 25.1. Tầng biên dịch và tính hợp lệ cấu trúc

- Mã Java biên dịch bằng JDK mục tiêu.
- Source có kiểu, khai báo, phụ thuộc và module path đúng.
- Biểu thức AOP được kiểm tra bởi compiler/parser tương ứng khi được hỗ trợ.
- Advice binding và loại join point có hợp đồng rõ.

**Mục tiêu:** loại lỗi cú pháp, kiểu và mô tả quy tắc can thiệp sớm nhất có thể.

### 25.2. Tầng weaving / cấu hình can thiệp

- Bộ dệt chạy với đúng phiên bản/cấu hình.
- Những class/call site cần thiết nằm trong phạm vi.
- Output sau weaving có thể được nạp và xác minh.
- Có ca kiểm tra dương: một điểm chắc chắn phải được can thiệp.
- Có ca kiểm tra âm: một điểm chắc chắn không được can thiệp.
- Cảnh báo về thiếu match được đánh giá theo yêu cầu nghiệp vụ.

**Mục tiêu:** chứng minh cơ chế thực sự kết hợp advice vào những nơi dự định.

### 25.3. Tầng runtime/integration

- Advice thực thi tại đúng join point đã chọn.
- Return value và exception của phần gốc được bảo toàn khi aspect chỉ quan sát.
- Around advice gọi `proceed` đúng số lần theo chính sách.
- Dữ liệu động/overload/annotation/`null` không làm advice lỗi.
- Thread lồng nhau/đồng thời và tác vụ bất đồng bộ không rò ngữ cảnh.
- Không có vòng lặp chặn lại ngoài ý muốn.
- Logging không làm lộ dữ liệu và không phá nghiệp vụ.

**Mục tiêu:** kiểm tra hành vi cuối cùng, không chỉ kiểm tra build hoặc việc có mã dệt.

## 26. Ma trận tình huống chẩn đoán

| Hiện tượng | Nhóm nghi ngờ đầu tiên | Bằng chứng cần lấy |
|---|---|---|
| `javac` từ chối kiểu trả về | Biên dịch Java | Vị trí source và kiểu khai báo |
| Pointcut parser báo ký pháp không hợp lệ | Xử lý biểu thức AOP | Dòng quy tắc và đặc tả cú pháp |
| Advice binding yêu cầu dữ liệu không có | Phân tích/binding weaving | Loại join point và tham số advice |
| Binary weaver không đọc được class version | Weaving/compatibility | Class version, JDK và phiên bản công cụ |
| Startup thất bại khi transform class | Load-time weaving | Stack trace transformer, class loader, class đích |
| `VerifyError` sau biến đổi | Bytecode verification, có thể do weaving | Artifact trước/sau và nguyên nhân verifier |
| `NoSuchMethodError` khi gọi | Binary linkage | Classpath, artifact runtime, signature |
| Ứng dụng chạy nhưng không thấy advice | Pointcut/weaving/path/logging | Một test dương/âm và đường đi thật |
| Lời gọi qua proxy có log; gọi target trực tiếp không | Runtime path của proxy | Tham chiếu object ở caller |
| Advice ném `NullPointerException` | Runtime logic | Stack trace, dữ liệu join point tại lần gọi |
| Nguyên nghiệp vụ ném nhưng caller thấy lỗi logger | Advice error handling | Cause/suppressed, khối finally |
| Around advice gọi phần gốc hai lần | Runtime continuation | Bộ đếm trong phần gốc, thứ tự advice |

Ma trận chỉ đưa ra **hướng điều tra ban đầu**. Phân loại cuối cùng phải dựa trên bằng chứng của hệ thống cụ thể.

## 27. Một quy trình chẩn đoán end-to-end

Khi nhận báo cáo “Aspect không hoạt động”, có thể dùng quy trình sau:

1. **Ghi triệu chứng chính xác:** build fail, startup fail, một lời gọi fail hay chỉ thiếu log?
2. **Xác định kiến trúc:** weaving lúc biên dịch, binary weaving, load-time weaving hay proxy/interceptor?
3. **Tái hiện tối thiểu:** một class, một pointcut, một advice, một lời gọi rõ ràng.
4. **Xác minh Java compilation:** mã nguồn/khả năng resolve kiểu và thư viện đã hợp lệ chưa?
5. **Xác minh phân tích AOP:** cú pháp pointcut, join point model, binding và warning.
6. **Xác minh weaving scope:** loại class, thời điểm nạp, class loader, phiên bản bytecode.
7. **Xác minh kết quả:** có artifact đã dệt hoặc bằng chứng adapter/proxy được thiết lập không?
8. **Xác minh runtime path:** caller có thật sự đi qua ranh giới được quan sát?
9. **Xác minh thứ tự thực thi:** ai bao ai, proceed có chạy hay short-circuit?
10. **Xác minh return/throw:** lỗi đến từ phần gốc, advice, logger hay liên kết class?
11. **Đưa vào kiểm thử hồi quy:** ca dương, ca âm, lỗi runtime và giới hạn độ bao phủ.
12. **Ghi lại nguyên nhân gốc:** phân biệt nguồn lỗi với triệu chứng và pha phát hiện.

**Không thay nhiều biến một lúc.** Ví dụ, nếu sửa pointcut, nâng JVM và thay class loader đồng thời rồi vấn đề biến mất, kết quả khó chứng minh nguyên nhân.

## 28. Lỗi dệt có thể bị phát hiện muộn — hãy nêu nhãn hai chiều

Một lỗi có thể có **bản chất weaving** nhưng **được phát hiện khi chạy**. Hữu ích khi báo cáo theo hai chiều:

~~~text
Nguồn lỗi:    cấu hình/pointcut/weaving/bytecode/runtime logic
Pha phát hiện: compile / binary transform / class loading / invocation
~~~

Ví dụ:

~~~text
Nguồn lỗi:    bytecode sau biến đổi không hợp lệ
Pha phát hiện: JVM class verification ở lúc class loading
~~~

Mô tả đó rõ hơn câu “lỗi runtime” vốn quá rộng.

Một ví dụ khác:

~~~text
Nguồn lỗi:    advice đọc nhầm chỉ số đối số
Pha phát hiện: invocation runtime
~~~

Đây thực sự là lỗi logic advice; không nên dồn nó vào “weaving failed” chỉ vì aspect có liên quan.

## 29. Bài tập tự kiểm tra

### Bài 1: Compile-time weaver báo lỗi

Một lệnh build dùng compiler có tích hợp weaving báo rằng binding của advice không phù hợp join point. Có nên nói đây là lỗi Java syntax thông thường không?

**Đáp án:** không. Lỗi xuất hiện trong build nhưng nguyên nhân thuộc **ràng buộc AOP/weaving**. Cần xem thông báo binding và đặc tả join point.

### Bài 2: Không có điểm khớp

Pointcut hợp lệ nhưng không khớp phương thức nào. Bộ dệt không báo lỗi nghiêm trọng. Đây có chắc là bug của weaver không?

**Đáp án:** không. Tập match rỗng có thể là kết quả hợp lệ; cần kiểm tra ý định pointcut và mức độ bắt buộc của độ bao phủ.

### Bài 3: Startup không nạp được class

Một class chỉ bị lỗi khi load-time transformer xử lý. Bạn cần kiểm tra gì?

**Đáp án:** stack trace transformer, class đang tải, class loader, phiên bản class/JVM, phạm vi weaving và artifact trước/sau nếu có. Không tự kết luận nghiệp vụ method đã chạy.

### Bài 4: Advice không in log qua target

`proxy.charge(10)` có dòng intercept, `target.charge(10)` không. Có phải Java compiler làm sai không?

**Đáp án:** không. Đây là giới hạn **đường gọi qua proxy**; gọi target trực tiếp không đi qua handler.

### Bài 5: Lỗi từ nghiệp vụ

Advice chạy, rồi `charge(-1)` ném `IllegalArgumentException` vì số tiền âm. Nhóm lỗi nào?

**Đáp án:** lỗi runtime do **hợp đồng/dữ liệu của nghiệp vụ gốc**; không chứng minh lỗi weaving.

### Bài 6: VerifyError sau dệt

Class ban đầu được JVM chấp nhận; bản sau biến đổi gây `VerifyError`. Kết luận ban đầu nên là gì?

**Đáp án:** nghi vấn có vấn đề ở quá trình biến đổi bytecode hoặc khả năng tương thích; phải so sánh artifact và xác minh môi trường trước khi kết luận cuối cùng.

### Bài 7: Lỗi cùng lúc

Nghiệp vụ ném lỗi A; advice cleanup ném lỗi B khiến caller chỉ thấy B. Có thể tìm nguyên nhân bằng cách chỉ sửa pointcut không?

**Đáp án:** không. Cần kiểm tra **exception masking** và chính sách lỗi của advice; bảo toàn/báo lỗi gốc theo hợp đồng.

### Bài 8: Runtime không có log nhưng nghiệp vụ thành công

Nêu tối thiểu bốn khả năng khác nhau.

**Đáp án gợi ý:** pointcut không match; lớp nằm ngoài weaving scope; loại join point không được hỗ trợ; caller đi ngoài proxy; nhánh chưa xảy ra; logger bị lọc hoặc sink lỗi.

### Bài 9: Binary compatibility

Biên dịch thành công, chạy gặp `NoSuchMethodError`. Có phải weaving chắc chắn là thủ phạm?

**Đáp án:** không. Có thể do classpath/runtime artifact khác với phiên bản đã dùng khi biên dịch, hoặc lỗi liên kết khác. Cần xác minh mã đích ở runtime.

### Bài 10: Kế hoạch retry

Around advice xử lý lỗi bằng cách gọi `proceed` thêm lần nữa. Hệ thống thanh toán ghi trùng một giao dịch. Đây có phải lỗi dệt?

**Đáp án:** thường là lỗi **thiết kế/hành vi runtime của advice và nghiệp vụ**, trừ khi có bằng chứng bộ dệt tạo mã sai. Phải đánh giá idempotency, giao dịch và chính sách retry.

## 30. Checklist trước khi báo “lỗi AOP”

- Tôi đã phân biệt **triệu chứng** với **nguyên nhân** chưa?
- Tôi biết cơ chế đang dùng là compile-time, binary weaving, load-time hay proxy không?
- Tôi đã xác định lỗi xảy ra khi **compile**, **transform/load** hay **invoke** chưa?
- Có phải lỗi cú pháp/kiểu Java thuần không?
- Pointcut có hợp lệ, đúng cú pháp và hỗ trợ đúng loại join point không?
- Binding tham số advice có phù hợp dữ liệu join point không?
- Có xác nhận class/call site nằm trong weaving scope không?
- Với proxy, lời gọi có thật sự qua proxy không?
- Có thể tái hiện bằng một test dương và một test âm không?
- Nếu có exception, tôi đã đọc **cause** và các lỗi phát sinh từ advice chưa?
- Nếu có `VerifyError` hoặc linkage error, tôi đã kiểm tra artifact/phiên bản/class loader chưa?
- Nếu advice không chạy, tôi có bằng chứng phần gốc vẫn chạy và kênh log còn hoạt động không?
- Với around advice, `proceed` có được gọi đúng số lần và có bảo toàn return/throw không?
- Tôi đã đưa ca tái hiện vào bộ kiểm thử hồi quy để tránh lỗi lặp lại chưa?

## 31. Kết luận

**Lỗi biên dịch** liên quan việc source không thỏa ngôn ngữ/hệ kiểu và khả năng phân giải. **Lỗi dệt** liên quan khả năng phân tích, chọn và kết hợp aspect với mã tại các join point được hỗ trợ. **Lỗi thực thi** liên quan những gì xảy ra khi chương trình và advice thực sự chạy: dữ liệu, trạng thái, ngoại lệ, continuation, đồng thời hoặc kết quả nghiệp vụ.

Ba nhãn không phải ba khoảng thời gian hoàn toàn độc lập. Một bộ dệt có thể chạy ngay khi biên dịch hoặc khi nạp class; một lỗi cấu hình weaving có thể chỉ lộ ở runtime, và một lỗi runtime có thể bắt nguồn từ advice chứ không phải phương thức gốc.

Để chẩn đoán chính xác, luôn hỏi hai câu: **“Vấn đề thuộc tầng nào?”** và **“Nó được phát hiện ở giai đoạn nào?”**. Sau đó kiểm chứng pointcut, join point model, weaving scope, runtime path và luồng return/throw bằng một ca thử nhỏ có thể tái hiện, thay vì quy mọi biểu hiện cho “AOP không hoạt động”.
