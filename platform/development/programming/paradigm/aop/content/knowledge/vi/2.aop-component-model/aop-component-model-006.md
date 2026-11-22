# Chương trình gốc, bộ dệt và kết quả sau khi dệt trong AOP

## 1. Ba thành phần tạo nên mô hình dệt aspect

Trong **Aspect-Oriented Programming (AOP)**, chương trình có thể được mô tả bằng hai nhóm quan tâm: hành vi chính của ứng dụng và các quy tắc xuyên cắt như quan sát thời gian chạy, kiểm toán, truy vết hay một số chính sách thực thi. **Weaving (dệt aspect)** là quá trình kết hợp các quy tắc xuyên cắt với những điểm thực thi được chọn, để hành vi cuối cùng bao gồm cả logic gốc lẫn phần được bổ sung.

Ba thành phần của mô hình cần hiểu là:

1. **Chương trình gốc (base program / target program):** những lớp, phương thức và luồng xử lý hiện có, trước khi áp dụng một bộ quy tắc aspect cụ thể.
2. **Bộ dệt (weaver):** cơ chế dùng định nghĩa aspect và quy tắc chọn điểm thực thi để gắn hành vi xuyên cắt vào đúng vị trí; cách gắn phụ thuộc thời điểm và công nghệ triển khai.
3. **Kết quả sau khi dệt (woven program / woven behavior):** chương trình hoặc cấu trúc thực thi có hành vi kết hợp. Khi dùng bytecode weaving, đó có thể là các tệp lớp đã biến đổi. Với interception bằng proxy, lớp gốc có thể không thay đổi trên đĩa, còn hành vi kết hợp tồn tại trong đường gọi qua proxy.

Công thức tư duy:

~~~text
Chương trình gốc ─────────────────────┐
                                      │
Định nghĩa aspect (pointcut + advice) ├──► Bộ dệt / cơ chế áp dụng
                                      │           │
Cấu hình, kiểu dữ liệu và môi trường ─┘           ▼
                                       Kết quả sau khi dệt
                                                  │
                                                  ▼
                                    Hành vi thực thi kết hợp
~~~

Hình trên là **mô hình khái niệm**. Không phải mọi cơ chế AOP đều chạy một bước biến đổi độc lập trước khi ứng dụng khởi động; có những cơ chế chèn hành vi khi tải lớp hoặc điều phối lời gọi ngay trong lúc chạy.

### Mục tiêu học tập

Sau bài này, bạn cần phân biệt được phần mã gốc với quy tắc aspect, giải thích cách bộ dệt xác định join point và gắn advice, dự đoán hành vi sau khi dệt, cũng như xác định được điều gì có thể quan sát trong tệp biên dịch và điều gì chỉ xuất hiện ở runtime.

## 2. Chương trình gốc: mô tả hành vi trước khi có aspect

**Chương trình gốc** là phần mã mang chức năng mà người dùng ứng dụng trực tiếp cần. Ví dụ một dịch vụ tính đơn giá:

~~~java
final class PriceCalculator {
    int total(int basePrice) {
        return basePrice + 20;
    }
}
~~~

Đây là **đoạn mã minh họa**, chưa phải chương trình độc lập có hàm main. Khi chưa áp dụng aspect, lời gọi **total(100)** trả về **120**; lớp chưa chứa thao tác ghi dấu bắt đầu hoặc kết thúc.

Cần hiểu đúng phạm vi của khái niệm “gốc”:

- **Ở mức source:** đó có thể là file Java được lập trình viên viết.
- **Ở mức mã biên dịch:** đó có thể là bytecode tạo ra từ Java trước bước dệt.
- **Ở mức một đối tượng đích:** đó có thể là instance thực thi nghiệp vụ mà một interceptor sẽ ủy quyền đến.

Vì vậy, câu nói “bộ dệt sửa chương trình gốc” cần được làm rõ. Có bộ dệt sửa bytecode; có cơ chế tạo đối tượng đại diện; có cơ chế thêm đường điều phối mà vẫn giữ nguyên file lớp gốc. Không thể suy ra hình dạng kết quả chỉ từ tên gọi “AOP”.

Chương trình gốc vẫn cần có trách nhiệm đúng, giao diện hợp lý và hành vi nghiệp vụ nhất quán. Weaving không tự sửa thiết kế miền sai hoặc bổ sung các bất biến bị thiếu.

## 3. Định nghĩa aspect là đầu vào thứ hai của quá trình dệt

Một aspect thường mô tả **điểm cần áp dụng** và **hành vi được áp dụng**. Các khái niệm liên quan:

| Khái niệm | Vai trò |
|---|---|
| **Join point** | Một điểm thực thi mà mô hình AOP hỗ trợ nhận diện: ví dụ lúc thực thi phương thức, tại lời gọi phương thức, hoặc khi truy cập trường dữ liệu tùy công nghệ. |
| **Pointcut** | Biểu thức hoặc quy tắc chọn những join point thuộc phạm vi cần xử lý. |
| **Advice** | Hành vi bổ sung chạy trước, sau, khi thất bại hoặc bao quanh join point. |
| **Aspect** | Đơn vị đóng gói pointcut, advice và có thể cả cấu hình, trạng thái hoặc các khai báo bổ sung. |
| **Target** | Lớp/đối tượng/mã thực thi gốc chịu tác động. |
| **Weaver** | Bộ xử lý kết hợp các quy tắc aspect với chương trình ở giai đoạn mà cơ chế hỗ trợ. |

Ví dụ **giả mã ngôn ngữ aspect trung lập với công cụ**, không phải cú pháp Java có thể đưa trực tiếp vào javac:

~~~text
aspect TracePrice
    pointcut pricedOperation =
        execution of PriceCalculator.total(int)

    before pricedOperation:
        print("trace: start")

    after-finally pricedOperation:
        print("trace: end")
end
~~~

Ý nghĩa của ví dụ là: chọn điểm **thực thi PriceCalculator.total(int)**; thực hiện một hành vi trước khi chạy mã gốc và một hành vi kết thúc bất kể đường ra thông thường hay ngoại lệ, theo quy tắc giả định. Nếu công nghệ được chọn không hỗ trợ loại join point hoặc advice đó, phải điều chỉnh cấu hình hoặc lựa chọn cơ chế khác.

Cần phân biệt:

- **Join point** là tập vị trí mà hệ thống *có khả năng* tác động.
- **Pointcut** chỉ chọn *một phần* trong tập đó.
- **Advice** quy định *làm gì* tại những vị trí đã chọn.
- **Weaver** quyết định *cách hiện thực* quy tắc trên mã hoặc đường gọi thực tế.

Pointcut không phải là câu lệnh trong thân hàm gốc; cũng không phải cứ một tên phương thức xuất hiện trong biểu thức là mọi lời gọi đến phương thức đó đều chắc chắn được chặn. Tính bao phủ phụ thuộc loại join point, quy tắc khớp và cơ chế dệt.

## 4. Bộ dệt thực hiện những công việc gì?

Dưới góc nhìn khái niệm, bộ dệt giải quyết năm vấn đề.

### 4.1. Nhận đầu vào và xây dựng ngữ cảnh

Bộ dệt cần biết những lớp/mã nào có thể tác động, định nghĩa aspect nào hoạt động và những quy tắc nào áp dụng. Tùy công cụ, đầu vào có thể là mã nguồn, các file đã biên dịch, thư viện trên classpath/module path, annotation, cấu hình tải lớp hoặc metadata về kiểu.

Ví dụ một pointcut chọn phương thức mang annotation sẽ cần cách đọc annotation thích hợp. Một pointcut chọn chữ ký phương thức cần thông tin về tên, tham số và kiểu. Các điều kiện phụ thuộc ngữ cảnh chạy có thể cần được kiểm tra muộn hơn so với giai đoạn đọc mã.

### 4.2. Tìm và kiểm tra các join point có thể áp dụng

Bộ dệt hoặc cơ chế interceptor xác định các điểm thực thi phù hợp với mô hình được hỗ trợ. Cần phân biệt:

- **Method execution:** điểm mã phương thức bắt đầu được thực thi.
- **Method call:** vị trí trong mã gọi một phương thức khác.
- **Field access:** đọc/ghi trường dữ liệu, nếu công nghệ hỗ trợ.
- **Các điểm khác:** khởi tạo đối tượng, constructor execution hoặc exception handler tùy mô hình và công nghệ.

Một lần gọi phương thức có thể liên quan cả **call join point** tại bên gọi và **execution join point** bên được gọi. Hai lựa chọn đó khác nhau về vị trí và số lượng điểm bị tác động. Công cụ chỉ hỗ trợ interception qua interface/proxy thường không quan sát được toàn bộ các điểm vừa kể.

### 4.3. Ghép advice vào đường thực thi

Khi một điểm khớp, bộ dệt chọn cách gắn **before**, **after**, **around** hoặc các loại advice được hỗ trợ. Một mẫu đơn giản có dạng:

~~~text
Caller
   │
   ▼
Advice trước
   │
   ▼
Hành vi gốc
   │
   ▼
Advice sau
   │
   ▼
Caller nhận kết quả
~~~

Sơ đồ này cố ý đơn giản: ngoại lệ, around advice, trả về sớm hoặc nhiều aspect có thể làm luồng thực tế phức tạp hơn. Với **around advice**, hành vi gốc không bắt buộc được gọi đúng một lần nếu công nghệ cho phép advice điều khiển **proceed**. Bỏ gọi proceed có thể bỏ qua hẳn công việc gốc; gọi nhiều lần có thể lặp tác dụng phụ. Đây là một năng lực mạnh đồng thời là rủi ro ngữ nghĩa.

### 4.4. Bảo toàn hợp đồng của lời gọi hoặc thay đổi có chủ đích

Weaving thường phải bảo toàn những yếu tố như chữ ký gọi được, kiểu trả về hợp lệ, khả năng lan truyền ngoại lệ và tính đúng đắn của mã biên dịch. Nhưng **bảo toàn chữ ký không đồng nghĩa bảo toàn hành vi**: aspect có thể thay giá trị trả về, ném lỗi mới, gây I/O, trì hoãn lời gọi hoặc từ chối gọi vào phương thức gốc.

Chính sách thiết kế phải nêu rõ điều gì được phép thay đổi. Ví dụ advice chỉ đo thời gian nên không âm thầm đổi giá trị trả về hoặc nuốt ngoại lệ. Advice thực hiện retry thì bắt buộc xét idempotency của hành vi gốc.

### 4.5. Tạo hiện vật đầu ra hoặc thiết lập cơ chế thực thi

Đầu ra có thể là:

- Bytecode đã dệt được lưu thành class/JAR.
- Bytecode được biến đổi khi lớp nạp vào JVM.
- Proxy/interceptor cùng một chuỗi gọi kết hợp tại runtime.

Do vậy, “kết quả sau khi dệt” cần được mô tả ở hai cấp: **hiện vật vật lý** (file/class/proxy/configuration) và **hành vi quan sát** (advice có chạy, chạy khi nào, có đổi kết quả hay không).

## 5. Từ chương trình gốc đến chương trình đã dệt: một ví dụ từng bước

Giả sử có lớp **PriceCalculator** ở phần 2, cùng quy tắc thực thi giả định:

- Trước mỗi lần thực thi **total(int)**, in **trace: start**.
- Khi phương thức kết thúc, kể cả khi ném ngoại lệ, in **trace: end**.
- Giữ nguyên phép tính giá và trả kết quả cho bên gọi.

### 5.1. Trước khi dệt

~~~java
final class PriceCalculator {
    int total(int basePrice) {
        return basePrice + 20;
    }
}
~~~

Luồng thực thi:

~~~text
Call total(100) → cộng 20 → trả về 120
~~~

### 5.2. Bộ dệt xử lý

Bộ dệt xác nhận có join point tương ứng với điểm thực thi **total(int)**, pointcut chọn được join point và advice được áp dụng theo trình tự đã định.

### 5.3. Mã sau dệt ở dạng mô phỏng dễ đọc

~~~java
// MÔ PHỎNG logic sau dệt; không phải mã nguồn chắc chắn được bộ dệt sinh ra.
final class PriceCalculatorWovenSketch {
    int total(int basePrice) {
        System.out.println("trace: start");
        try {
            return basePrice + 20;
        } finally {
            System.out.println("trace: end");
        }
    }
}
~~~

Khi gọi **total(100)**, hành vi mong đợi:

~~~text
trace: start
trace: end
~~~

Sau đó caller nhận giá trị **120**. Trong trường hợp thêm lệnh **System.out.println(result)** ở caller, dòng **120** mới xuất hiện trên stdout. Bản thân phương thức chỉ trả số nguyên, không tự in kết quả.

**Chú ý về phạm vi minh họa:** bộ dệt thật có thể chèn instruction, tạo method phụ, thay đổi call site, thêm wrapper hoặc dùng hình thức khác; không nhất thiết tạo đúng Java source như lớp minh họa. Nội dung có ý nghĩa ở đây là **hành vi thực thi**, không phải lời khẳng định về hình dạng bytecode.

### 5.4. Mã đầu ra có thể khác nhau nhưng quan sát giống nhau

Hai triển khai khác nhau có thể đều ghi dòng bắt đầu/kết thúc và trả về 120:

1. Biến đổi trực tiếp bytecode của **PriceCalculator**.
2. Giữ **PriceCalculator** nguyên vẹn, nhưng caller sử dụng một đối tượng bao ngoài hoặc proxy chặn lời gọi.

Kết quả quan sát ở đường gọi được chọn giống nhau, nhưng **khả năng bao phủ** khác nhau. Nếu caller giữ tham chiếu trực tiếp đến đối tượng gốc và gọi mà không đi qua proxy, phương án thứ hai có thể bỏ qua advice.

Đó là lý do không nên kết luận từ stdout rằng hệ thống đã thực hiện compile-time weaving.

## 6. Phân biệt thời điểm dệt và loại đầu ra

Ở đây câu hỏi chính không chỉ là *weaving xảy ra lúc nào* mà là **hiện vật nào được tạo ra và caller đang chạy bản nào**. Cùng một aspect có thể tạo kết quả vật lý khác nhau:

| Cơ chế | Đầu vào chính | Đầu ra cần kiểm chứng | Sai sót dễ bỏ qua |
| --- | --- | --- | --- |
| **Compile-time weaving** | Mã nguồn, aspect, compiler hỗ trợ | Class/JAR sau biên dịch đã có advice | Chạy nhầm output từ compiler thường |
| **Post-compile/binary weaving** | Class/JAR gốc, aspect và weaver | **Bản binary mới**, giữ tách khỏi bản gốc | Đóng gói nhầm JAR chưa weave hoặc dùng lại output làm input |
| **Load-time weaving** | Bytecode, agent/transformer và cấu hình | Định nghĩa lớp đã biến đổi trong JVM; file đĩa có thể giữ nguyên | Class đã load sớm, sai classloader hoặc agent không bật |
| **Runtime proxy/interception** | Target, proxy/chuỗi interceptor | Đối tượng trung gian và đường gọi qua nó; class target có thể giữ nguyên | Caller nắm target thô hoặc self-invocation bỏ qua proxy ủy quyền |

**Bài kiểm tra artifact:** giả sử `PriceCalculator.java` tạo ra `out/plain/PriceCalculator.class`, sau đó một bước binary weaving sinh `out/woven/PriceCalculator.class`. Test phải **nạp bản trong `out/woven`** để quan sát advice. Với proxy, kiểm tra receiver có là proxy hay không; với load-time weaving, kiểm tra **định nghĩa lớp** đã được biến đổi chứ không chỉ thấy JAR agent trên classpath.

Compile-time weaving thuận tiện khi muốn kiểm chứng artifact trước phát hành nhưng cần toolchain phù hợp và có thể phải build lại. Binary weaving đòi hỏi quản lý cả trước/sau. Load-time weaving phụ thuộc thời điểm nạp lớp, cấu hình và classloader. Proxy dễ lắp ở API boundary nhưng không tự chặn đường gọi bỏ qua nó. Đây là **phân tích đầu ra của quá trình dệt**, không đánh đồng proxy với biến đổi bytecode.

## 7. Ví dụ Java 17 chạy được: trước và sau khi thêm lớp chặn

Để quan sát sự khác biệt mà không cần cài công cụ AOP riêng, chương trình sau xây dựng ba đường gọi:

1. Gọi **BasePriceService** trực tiếp, đại diện cho đường đi của chương trình gốc.
2. Gọi qua **WrappedPriceService**, mô phỏng hành vi sau khi một bộ dệt chèn before/finally quanh lời gọi.
3. Gọi qua **JDK dynamic proxy**, minh họa một cơ chế interception ở runtime.

Cần phân biệt chính xác: hai đường gọi cuối **chỉ minh họa hiệu ứng kết hợp hành vi và giới hạn của wrapper/proxy**; chương trình demo không thực hiện một bước bytecode weaving thực sự.

Tạo file **WeavingModelDemo.java**:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;

public class WeavingModelDemo {
    interface PriceService {
        int quote(int base);
    }

    static final class BasePriceService implements PriceService {
        public int quote(int base) {
            System.out.println("core: quote");
            return base + 20;
        }
    }

    static final class WrappedPriceService implements PriceService {
        private final PriceService target;

        WrappedPriceService(PriceService target) {
            this.target = target;
        }

        public int quote(int base) {
            System.out.println("advice: before");
            try {
                return target.quote(base);
            } finally {
                System.out.println("advice: after");
            }
        }
    }

    static PriceService intercepted(PriceService target) {
        return (PriceService) Proxy.newProxyInstance(
                PriceService.class.getClassLoader(),
                new Class<?>[] {PriceService.class},
                (proxy, method, args) -> {
                    System.out.println("advice: before");
                    try {
                        return method.invoke(target, args);
                    } catch (InvocationTargetException exception) {
                        throw exception.getCause();
                    } finally {
                        System.out.println("advice: after");
                    }
                });
    }

    public static void main(String[] args) {
        PriceService original = new BasePriceService();
        System.out.println("original = " + original.quote(100));

        PriceService wrapped = new WrappedPriceService(original);
        System.out.println("wrapped = " + wrapped.quote(100));

        PriceService proxy = intercepted(original);
        System.out.println("proxy = " + proxy.quote(100));
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac --release 17 WeavingModelDemo.java
java WeavingModelDemo
~~~

Stdout chính xác:

~~~text
core: quote
original = 120
advice: before
core: quote
advice: after
wrapped = 120
advice: before
core: quote
advice: after
proxy = 120
~~~

Đọc kết quả:

- **original:** chỉ mã lõi chạy, vì đối tượng gốc không được bao bởi một interceptor trong đường gọi đó.
- **wrapped:** phần before và phần finally bao quanh lần thực thi lõi, kết quả 120 không đổi.
- **proxy:** cuộc gọi qua JDK dynamic proxy kích hoạt handler; handler gọi method gốc bằng reflection, rồi phần finally chạy.

Việc bắt **InvocationTargetException** và ném lại **getCause()** giữ ngoại lệ gây ra bởi phương thức đích, thay vì bắt caller nhận một lớp bọc do reflection. Ví dụ tập trung vào phương thức **quote** và không chứng minh rằng mọi phương thức của Java đều có thể bị proxy chặn trong mọi môi trường.

### Tại sao kết quả ba đường đi không giống kết quả ba chương trình đã dệt khác nhau?

Vì chúng đều chạy trong **một chương trình minh họa** có ba đối tượng. Bước thứ hai là Decorator được lập trình viên viết; bước thứ ba là JDK proxy. Một bytecode weaver thực thụ có thể tạo đường thực thi tương tự nhưng artifact, ngữ nghĩa join point và quy tắc chọn phương thức phải được kiểm chứng trên công cụ thực. Demo chỉ giúp nhìn thấy điều cần dự đoán khi học mô hình dệt.

## 8. Hình dạng kết quả sau dệt: vật lý và ngữ nghĩa

Để tránh nhầm lẫn, đánh giá kết quả theo hai câu hỏi.

### 8.1. Hiện vật vật lý thay đổi ra sao?

Các khả năng bao gồm:

- **Tệp class thay đổi:** mã máy ảo bổ sung lời gọi đến advice, cấu trúc method, metadata hoặc thành phần phụ trợ.
- **JAR đã được dệt:** artifact được đóng gói từ những class đầu ra đã qua bước binary/compile-time weaving.
- **Định nghĩa lớp trong JVM thay đổi:** bộ biến đổi cung cấp bytecode đã dệt khi tải lớp, nhưng bản trên đĩa có thể chưa được dệt.
- **Đối tượng proxy mới:** class gốc giữ nguyên, thay đổi nằm ở đối tượng đại diện và đường gọi được lắp ghép.

Không phải mọi bộ dệt đều sinh ra file **.java**. Việc decompile một class có thể giúp hình dung luồng nhưng mã decompile không nhất thiết tương ứng với cấu trúc nguồn và thứ tự debug ban đầu.

### 8.2. Hành vi ngữ nghĩa thay đổi ra sao?

Đây mới là tiêu chí đánh giá chính khi viết Knowledge:

- Join point nào thực sự có advice chạy?
- Advice chạy trước, sau, khi có ngoại lệ hay bao quanh?
- Chạy bao nhiêu lần trên một lời gọi?
- Giá trị trả về, ngoại lệ và các tác dụng phụ có giữ nguyên không?
- Có thể đi theo một đường khác để bỏ qua advice không?
- Khi nhiều aspect cùng áp dụng thì thứ tự là gì?

Một class thay đổi bytecode **không bảo đảm** rule mong muốn đã áp dụng chính xác. Ngược lại, một proxy làm thay đổi hành vi mà không có file class gốc nào bị sửa.

## 9. Matching ở lúc dệt và điều kiện quyết định khi chạy

Không phải mọi pointcut đều có thể được giải quyết hoàn toàn từ mã tĩnh.

Ví dụ:

- **Điều kiện tĩnh:** một phương thức có chữ ký xác định hoặc mang annotation đánh dấu, nếu bộ dệt có thể nhìn thấy metadata đó.
- **Điều kiện động:** chỉ ghi nhận nếu tham số tại thời điểm gọi thỏa điều kiện hoặc context của tác vụ có giá trị nhất định.

Bộ dệt có thể xác định tập vị trí tiềm năng ở giai đoạn compile/load, rồi để lại các điều kiện kiểm tra khi chương trình chạy. Cũng có công nghệ đánh giá selector khi interceptor nhận lời gọi.

Vì vậy, cần phân biệt ba tập:

1. **Join point được mô hình AOP hỗ trợ**.
2. **Join point có thể khớp pointcut theo thông tin đã biết**.
3. **Join point thực sự kích hoạt advice trong một lần chạy cụ thể**.

Thống kê “có bao nhiêu phương thức khớp ở lúc biên dịch” và “advice đã chạy bao nhiêu lần” trả lời hai câu hỏi khác nhau. Đường đi điều kiện, lazy loading, ngoại lệ hoặc lời gọi bất đồng bộ có thể khiến số lần thực thi nhỏ hoặc lớn hơn số điểm tĩnh.

## 10. Vấn đề thứ tự khi nhiều aspect cùng áp dụng

Giả sử một thao tác được cả **Tracing** và **Retry** bao quanh.

~~~text
Tracing(Retry(Core))
  → Tracing nhìn một chu kỳ gồm tất cả lần thử.

Retry(Tracing(Core))
  → Tracing có thể nhìn riêng từng lần thử.
~~~

Sự khác biệt chỉ đúng khi các wrapper/advice hiện thực những hành vi như trong sơ đồ, nhưng nó cho thấy thứ tự ghép ảnh hưởng **ý nghĩa đầu ra**, không chỉ hình thức. Khi có before/after từ nhiều aspect, việc “cái nào chạy trước” cần được xác định qua cơ chế precedence/order của công cụ và kiểm thử thực tế.

Một ví dụ khác:

~~~text
Before A
    Before B
        Core
    After B
After A
~~~

Đây là **một thứ tự lồng nhau hợp lệ**, không phải quy luật mặc định cho mọi công cụ. Nếu hai aspect không có thứ tự ổn định, việc phụ thuộc vào trình tự log hoặc thay đổi trạng thái là một lỗi thiết kế.

Một **around advice** có thể bỏ qua lời gọi lõi nếu nó không chuyển tiếp, hoặc có thể lặp lời gọi nếu nó retry; kết quả sau dệt vì thế có thể khác rõ so với chương trình gốc. Nếu lõi có thao tác gửi tiền hoặc phát thông điệp, việc lặp gọi cần có bảo đảm chống thực hiện trùng.

## 11. Các ranh giới dễ gây hiểu sai về phạm vi dệt

### 11.1. Self-invocation qua proxy

Xét đoạn code khái niệm:

~~~java
void outer() {
    inner();
}

void inner() {
    // Xử lý cần theo dõi
}
~~~

Nếu đối tượng **outer** đang chạy là target gốc và lời gọi **inner()** được thực hiện nội bộ, bộ chặn dựa hoàn toàn vào proxy bên ngoài có thể không nhìn thấy lời gọi đó. Với một cơ chế dệt bytecode hỗ trợ join point **execution của inner**, advice vẫn có thể được áp dụng. Muốn dự đoán chính xác, phải biết **loại join point và đường đi thực tế**.

### 11.2. Lời gọi phương thức không đồng nghĩa truy cập trường

Một proxy method-call không tự động trở thành bộ chặn read/write của field. Nếu cần aspect theo dõi field access hoặc constructor, phải xác minh công cụ có loại join point này. Không nên khẳng định mọi annotation hoặc mọi thành viên trong lớp đều được xử lý như nhau.

### 11.3. Một class có nhiều loader hoặc không nằm trong phạm vi weaving

Ở những hệ thống sử dụng class loader, cùng một tên class có thể được nạp dưới nhiều danh tính lớp khác nhau. Cấu hình dệt phải áp dụng đến đúng vùng lớp đang được dùng. Một class được nạp trước khi transformer được thiết lập có thể không tự được sửa về sau, trừ khi công nghệ hỗ trợ và thực hiện retransformation/redefinition phù hợp.

### 11.4. Source giữ nguyên không chứng minh advice không hoạt động

Biên dịch hoặc load-time weaving có thể làm đường thực thi thay đổi dù người đọc file Java chỉ thấy mã nghiệp vụ. Vì vậy, khi điều tra lỗi không thể chỉ tìm bằng văn bản xem thân phương thức có gọi helper hay không; cần xem công cụ dệt, điểm chọn và artifact/runtime.

### 11.5. Thoát bằng ngoại lệ khác trả về thành công

**After-returning** và **after-throwing** diễn tả những tình huống khác nhau; **after-finally** có thể dùng để đảm bảo phần kết thúc chạy khi cả đường thành công hoặc lỗi, tùy ngữ nghĩa công cụ. Không nên ghi “thao tác thành công” trong advice chỉ được chứng minh là phương thức đã kết thúc. Đặc biệt, một phương thức trả về đối tượng biểu diễn công việc bất đồng bộ chưa có nghĩa công việc đó đã hoàn thành.

## 12. Bộ dệt và hợp đồng đúng đắn của chương trình

Một bài phân tích weaving tốt phải vượt qua câu hỏi “có in thêm log không?” để xem **hợp đồng thực thi**.

### 12.1. Giá trị trả về

Nếu target trả về số **120**, advice quan sát thuần túy nên để caller tiếp tục nhận **120**. Với **around advice** được phép thay kết quả, thay đổi phải là một phần chính sách có chủ đích và tương thích với hợp đồng phương thức.

### 12.2. Ngoại lệ

Nếu target ném lỗi, interceptor nên có chính sách rõ về việc truyền tiếp, chuyển đổi hoặc ghi nhận. Nuốt ngoại lệ trong advice vô tình biến thất bại thành thành công và có thể làm hỏng invariant của caller. Một exception do chính advice ném ra cũng có thể thay thế exception gốc; cần quyết định cách ưu tiên và ghi nhận lỗi.

### 12.3. Tác dụng phụ

Log hoặc đo metric có thể có lỗi I/O. Trong một số hệ thống, lỗi quan sát không nên làm hỏng nghiệp vụ; trong hệ thống kiểm toán bắt buộc, thất bại ghi nhận có thể phải chặn thao tác. Đây là quyết định chính sách, không phải hành vi mặc định của từ khóa advice.

### 12.4. Concurrency và trạng thái aspect

Nếu aspect lưu trạng thái chia sẻ giữa nhiều lời gọi, cần xét an toàn luồng và reentrancy. Nếu lưu context theo thread, công việc bất đồng bộ có thể chạy trên thread khác; phải có chiến lược truyền context phù hợp. Weaving không tự giải quyết các vấn đề đồng bộ.

### 12.5. Bảo mật và dữ liệu

Advice ghi tham số hay giá trị trả về có thể vô tình lưu thông tin nhạy cảm. Bộ dệt chỉ gắn hành vi vào đúng vị trí; nó không quyết định dữ liệu nào được phép thu thập. Những pointcut áp dụng rộng phải được kiểm soát phạm vi và dữ liệu đầu ra.

## 13. Cách kiểm chứng một kết quả sau khi dệt

Quy trình kiểm tra nên phân biệt **đã nạp/cấu hình bộ dệt** với **advice thực sự chạy**.

### Bước 1 — Xác định hợp đồng dự kiến

Ghi rõ lớp/method nào cần khớp, loại join point, advice nào áp dụng, ngoại lệ dự kiến và yêu cầu thứ tự. Ví dụ: mọi lần **PriceService.quote** được gọi qua đường chặn cụ thể đều ghi begin/end đúng một lần, vẫn trả cùng kết quả.

### Bước 2 — Kiểm tra cấu hình và hiện vật

Tùy cơ chế:

- Với compile-time/binary weaving, kiểm tra artifact triển khai là bản đã dệt.
- Với load-time weaving, kiểm tra transformer/agent và phạm vi tải lớp đã hoạt động.
- Với proxy, kiểm tra caller đang giữ tham chiếu proxy thay vì target trực tiếp.

Có thể dùng các công cụ kiểm tra class/bytecode thích hợp hoặc thông tin chẩn đoán của weaver, nhưng tránh coi việc nhìn thấy một instruction đơn lẻ là bằng chứng đầy đủ về mọi lần chạy.

### Bước 3 — Kiểm tra hành vi ở đường đi thật

Tạo ca có khớp pointcut và ca không khớp. Với ca khớp, kiểm tra số lần advice chạy, kết quả trả về và thứ tự. Với ca không khớp, bảo đảm advice không kích hoạt sai.

### Bước 4 — Kiểm tra ca biên

Bao gồm ngoại lệ, nhiều aspect cùng khớp, gọi lồng nhau, self-invocation nếu dùng proxy, đường gọi trực tiếp vào target, chạy song song và bất đồng bộ khi có liên quan. Đặc biệt kiểm tra điều kiện động của pointcut tại runtime.

### Bước 5 — Đối chiếu hành vi cũ và mới

Tách phép so sánh thành:

| Thuộc tính | Trước dệt | Sau dệt | Câu hỏi cần kiểm chứng |
|---|---|---|---|
| Kết quả nghiệp vụ | Trả **120** | Thường vẫn **120** với advice quan sát thuần túy | Có bị thay giá trị không? |
| Side effect kỹ thuật | Không có trace | Có trace trước/sau | Đúng vị trí, đúng số lần chứ? |
| Ngoại lệ | Truyền lỗi gốc | Có thể thêm ghi nhận lỗi | Có nuốt hoặc đổi lỗi ngoài ý muốn không? |
| Đường gọi | Caller đến target | Có thể qua proxy hoặc mã biến đổi | Có đường đi bỏ qua advice không? |
| Hiện vật | Class/chương trình chưa dệt | Class dệt, lớp nạp đã biến đổi hoặc runtime proxy | Bộ dệt thực tế đã tác động vào đâu? |

## 14. Những sai lầm thường gặp

**Sai lầm 1 — Xem aspect là mã tự chạy chỉ vì đã khai báo.** Một khai báo aspect phải được cơ chế AOP nhận diện và áp dụng. Nếu weaver chưa được kích hoạt hoặc pointcut không khớp, hành vi mong muốn có thể không xuất hiện.

**Sai lầm 2 — Nghĩ kết quả sau dệt luôn là một file Java mới.** Phần lớn phân tích thực tế phải nhìn ở lớp bytecode, class loading hoặc đường chặn lời gọi; mã nguồn Java có thể không đổi.

**Sai lầm 3 — Nhầm static weaving với proxy.** Weaving có thể tác động trực tiếp vào vị trí thực thi đã chọn, còn proxy thường phụ thuộc lời gọi đi qua đại diện. Không thể lấy hạn chế của một công cụ để suy ra giới hạn phổ quát của AOP.

**Sai lầm 4 — Chỉ kiểm tra một đường thành công.** Kết quả có thể đúng ở đường thường nhưng advice bị bỏ qua khi gọi nội bộ, chạy lặp khi retry, hoặc xử lý ngoại lệ không đúng.

**Sai lầm 5 — Xem pointcut là không thể bị ảnh hưởng bởi refactor.** Đổi tên package, annotation, method hoặc cách tổ chức lớp có thể làm tập điểm khớp khác đi. Cần kiểm thử phạm vi và cách đặt tên ổn định.

**Sai lầm 6 — Cho rằng after luôn đồng nghĩa thành công.** Advice chạy khi phương thức kết thúc không đảm bảo thao tác nghiệp vụ đã commit hoặc tác vụ bất đồng bộ đã xong.

**Sai lầm 7 — Bỏ qua thứ tự aspect.** Các advice lồng nhau có thể đổi nghĩa phép đo, transaction, retry hoặc cache. Khi thứ tự là điều kiện đúng đắn, phải đặc tả và kiểm chứng.

**Sai lầm 8 — Giả định woven artifact đồng nhất trên mọi máy.** Đầu vào classpath, phiên bản compiler/weaver, class loader và cấu hình có thể ảnh hưởng kết quả. Build và runtime phải có khả năng tái lập, quan sát được.

## 15. Bài tập suy luận từ ba thành phần

### Bài tập 1: Bộ dệt có tạo file mới không?

Một ứng dụng dùng proxy để bọc **PriceService**. File **BasePriceService.class** không thay đổi, nhưng log advice xuất hiện khi gọi qua interface.

**Hỏi:** có thể xem đó là chương trình có hành vi kết hợp không? Có thể kết luận đã biến đổi bytecode của BasePriceService không?

**Gợi ý:** hành vi kết hợp là có trên đường proxy; không có căn cứ nói class gốc đã được sửa.

### Bài tập 2: Cùng source, khác kết quả

Hai lần triển khai từ cùng source: môi trường A kích hoạt load-time weaving, môi trường B bỏ qua cấu hình bộ biến đổi. B có chạy advice chắc chắn không?

**Gợi ý:** không; cần kiểm tra thực tế bộ dệt và lớp được áp dụng. Source giống nhau chưa đủ khẳng định hành vi giống nhau.

### Bài tập 3: Chọn đúng join point

Muốn ghi dấu **mỗi lần thực thi** của phương thức X, nhưng pointcut lại chọn các vị trí **gọi X** trong chỉ một nhóm caller.

**Hỏi:** có thể bỏ sót khi X được gọi từ nơi khác không?

**Gợi ý:** có. Call join point của một tập caller không giống execution join point tại chính X.

### Bài tập 4: Around advice bỏ qua hành vi gốc

Một advice nhận lời gọi nhưng trả về giá trị mặc định mà không gọi tiếp vào hành vi gốc.

**Hỏi:** chương trình sau dệt còn giữ chắc chắn chức năng ban đầu không?

**Gợi ý:** không. Nếu không có bảo đảm rõ về quy tắc này, bộ dệt hoặc advice đã thay đổi ngữ nghĩa nghiệp vụ.

### Bài tập 5: Kiểm thử tương đương

Chương trình chưa dệt trả 120. Chương trình đã dệt cũng trả 120 nhưng ghi hai lần cùng một metric. Chỉ dùng assert kết quả 120 đã đủ chưa?

**Gợi ý:** chưa; cần kiểm tra hiệu ứng bổ sung, số lần và thứ tự advice, đồng thời xác minh các đường lỗi và đường gọi ngoài phạm vi.

## 16. Sơ đồ ghi nhớ để đọc một hệ thống AOP bất kỳ

~~~text
(1) BASE PROGRAM
    Source / bytecode / đối tượng target
    "Hành vi gốc là gì?"
                │
                ├─────────────────┐
                │                 │
(2) ASPECT SPECIFICATION          │
    Pointcut: ở đâu?              │
    Advice: làm gì?               │
    Precedence: thứ tự?           │
                │                 │
                ▼                 ▼
(3) WEAVER / INTERCEPTOR MECHANISM
    Compile / post-compile / load / runtime
    "Loại join point nào thực sự được hỗ trợ?"
                │
                ▼
(4) WOVEN RESULT
    Bytecode biến đổi hoặc đường gọi qua proxy
    "Hiện vật nào thay đổi?"
                │
                ▼
(5) OBSERVED EXECUTION
    Advice nào chạy, lúc nào, bao nhiêu lần?
    Target có được gọi? Kết quả và lỗi ra sao?
~~~

Khi gặp một công nghệ AOP mới, trước tiên xác định **mã gốc, định nghĩa aspect, cơ chế dệt và điểm áp dụng thực tế**. Sau đó phân biệt **artifact sau dệt** với **hành vi quan sát khi chạy**. Hai bước này giúp đọc và chẩn đoán một hệ thống aspect đúng về mặt kỹ thuật, kể cả khi chương trình gốc không chứa lời gọi trực tiếp đến logic xuyên cắt.