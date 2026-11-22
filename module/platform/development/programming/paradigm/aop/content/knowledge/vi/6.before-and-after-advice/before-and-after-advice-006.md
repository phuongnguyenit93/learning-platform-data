# Thứ tự advice trong trường hợp có nhiều lớp can thiệp

Khi chỉ có một advice ở một điểm nối (join point), ta có thể hình dung đơn giản: mã **before** chạy trước nghiệp vụ, mã **after** chạy sau nghiệp vụ. Nhưng trong lập trình hướng khía cạnh (**Aspect-Oriented Programming – AOP**), một join point có thể được nhiều aspect hoặc nhiều advice cùng chọn. Lúc đó, câu hỏi quan trọng không còn chỉ là “advice nào chạy?” mà còn là **“chạy theo thứ tự nào, cái nào bao ngoài cái nào, và kết quả sẽ ra sao nếu một lớp chặn, ném lỗi hoặc thay đổi kết quả?”**.

Đây không chỉ là vấn đề thứ tự dòng log. Thứ tự có thể quyết định kiểm tra quyền xảy ra trước hay sau khi mở giao dịch, phép đo thời gian có bao gồm kiểm tra quyền không, ngoại lệ có đi tới lớp rollback không, và dữ liệu nào được ghi lại khi nghiệp vụ thất bại.

Bài viết trình bày các quy tắc tư duy tổng quát, dùng mô hình advice lồng nhau và ví dụ Java 17 có thể chạy độc lập. **Không tồn tại một thứ tự mặc định phổ quát cho mọi hệ thống AOP.** Cú pháp khai báo độ ưu tiên, cách kết hợp advice, xử lý trường hợp đồng mức và một số ngữ nghĩa phụ thuộc vào mô hình join point/weaving của công cụ cụ thể.

## 1. Từ một advice đến nhiều lớp can thiệp

Trong AOP:

- **Join point** là một điểm thực thi được mô hình hỗ trợ can thiệp, chẳng hạn method call hoặc method execution.
- **Pointcut** chọn tập join point mà một advice/aspect quan tâm.
- **Advice** là xử lý bổ sung trước, sau hoặc bao quanh điểm đó.
- **Aspect** nhóm các pointcut, advice và trạng thái liên quan tới một mối quan tâm cắt ngang.
- **Weaving/combination** quyết định cách hành vi bổ sung được kết hợp với luồng nghiệp vụ.

Giả sử thao tác `pay()` đồng thời chịu ba mối quan tâm:

1. **Kiểm soát quyền:** từ chối yêu cầu không có quyền thanh toán.
2. **Giao dịch:** chuẩn bị tài nguyên, commit khi thành công, rollback khi thất bại.
3. **Quan sát:** ghi log và đo độ trễ.

Nếu cả ba cùng áp dụng tại một điểm, việc “có cả ba” chưa đủ bảo đảm đúng. Một thứ tự là kiểm tra quyền **trước** khi mở tài nguyên giao dịch; một thứ tự khác là mở giao dịch rồi mới kiểm tra quyền. Cả hai đều có thể được một cơ chế kết hợp tạo ra, nhưng chi phí và ngữ nghĩa khác nhau.

Điều đầu tiên cần xác định là **tập advice thực sự áp dụng**. Hai advice chỉ có thể tranh thứ tự tại một lần thực thi nếu pointcut của chúng đều khớp join point đang xét và cơ chế thật sự can thiệp được tại điểm đó. Quy tắc chọn điểm và quy tắc sắp xếp là **hai trách nhiệm riêng**.

## 2. Tư duy chính: các lớp lồng nhau

Với các xử lý kiểu **around** có quyền tiếp tục gọi hành vi kế tiếp, một cách hiểu trực quan là tạo các lớp bọc:

~~~text
Bên gọi
  |
  v
[OUTER: kiểm tra quyền]
  |
  v
[MIDDLE: giao dịch]
  |
  v
[INNER: ghi log]
  |
  v
[NGHIỆP VỤ]
  |
  v
[INNER: kết thúc ghi log]
  |
  v
[MIDDLE: kết thúc giao dịch]
  |
  v
[OUTER: kết thúc]
  |
  v
Bên gọi nhận kết quả/ngoại lệ
~~~

Đây là **một thứ tự lồng nhau do ta lựa chọn để minh họa**, không phải thứ tự bắt buộc của bất kỳ nền tảng nào.

Một lớp bao ngoài thường **đi vào trước** lớp bên trong; khi các lớp cho phép gọi tiếp và thực thi bình thường, quá trình kết thúc diễn ra theo chiều **ngược lại**:

- **Đi vào:** Outer → Middle → Inner → nghiệp vụ.
- **Đi ra:** nghiệp vụ → Inner → Middle → Outer.

Mẫu này tương tự các lời gọi hàm lồng nhau và cơ chế ngăn xếp (stack), thường được gọi là “vào trước, ra sau” trong cách tổ chức wrapper.

Tuy nhiên, đừng suy rộng rằng **mọi advice before/after đều được triển khai bằng wrapper**. Hệ thống AOP có thể weave advice ở các điểm trước/sau cụ thể hoặc áp dụng quy tắc ưu tiên riêng. Mô hình lồng nhau ở đây giúp phân tích hành vi; với nền tảng thật, phải xác minh thứ tự theo hợp đồng của nó.

## 3. Các loại advice và thứ tự trong mỗi nhánh

Các dạng phổ biến theo ý nghĩa:

| Advice | Thời điểm | Khi nhiều lớp lồng nhau |
| --- | --- | --- |
| **Before** | Trước khi phần được can thiệp bắt đầu | Ở mô hình wrapper: outer trước inner |
| **After returning / success** | Sau khi phần được can thiệp kết thúc bình thường | Inner xử lý thành công rồi outer |
| **After throwing / error** | Sau khi phần được can thiệp kết thúc bằng ngoại lệ | Inner quan sát lỗi rồi outer, nếu lỗi được truyền tiếp |
| **After / finally** | Khi thoát phạm vi dù thành công hay thất bại | Inner kết thúc/cleanup trước outer |
| **Around** | Bao lấy phần thực thi kế tiếp | Có thể thực hiện trước/sau, gọi tiếp, chặn hoặc xử lý kết quả và lỗi |

Các tên và khả năng chính xác khác nhau theo cơ chế AOP. Đặc biệt, **after returning không đồng nghĩa finally**; nhánh thành công không chạy khi phần được bao quanh kết thúc bằng ngoại lệ. **After throwing** cũng không được xem như đoạn chạy bắt buộc sau mọi lời gọi; nó gắn với đường lỗi theo hợp đồng.

### 3.1 Nhánh thành công

~~~text
OUTER before
  MIDDLE before
    INNER before
      BUSINESS success
    INNER after-success
    INNER finally
  MIDDLE after-success
  MIDDLE finally
OUTER after-success
OUTER finally
~~~

Nếu các lớp cùng có xử lý success và finally, thứ tự cụ thể của **success trước finally** trong đoạn mô tả trên đến từ cấu trúc `try/catch/finally` minh họa ở phần ví dụ. Không tự lấy sơ đồ này làm tuyên bố về ưu tiên giữa các loại advice được khai báo độc lập trong mọi công cụ.

### 3.2 Nhánh thất bại

~~~text
OUTER before
  MIDDLE before
    INNER before
      BUSINESS throws error
    INNER after-error
    INNER finally
  MIDDLE after-error
  MIDDLE finally
OUTER after-error
OUTER finally
CALLER receives error
~~~

Nếu lớp trong **nuốt ngoại lệ và trả về một kết quả bình thường**, lớp ngoài có thể thấy **thành công**, chứ không còn thấy lỗi. Nếu lớp trong ném **ngoại lệ mới**, lớp ngoài thấy ngoại lệ mới. Như vậy, **thứ tự và khả năng thay đổi luồng điều khiển của advice ảnh hưởng trực tiếp tới các nhánh chạy**.

### 3.3 Vì sao finally có giá trị?

Các việc như dừng đồng hồ, xóa ngữ cảnh tạm, trả tài nguyên hoặc ghi nhận kết thúc nên được đặt ở cơ chế **được bảo đảm thực thi lúc rời phạm vi tương ứng**. Trong Java, `finally` là một công cụ diễn đạt hành vi này. Tuy nhiên, một lỗi mới ném trong `finally` vẫn có thể che mất ngoại lệ ban đầu hoặc thay đổi kết quả; mã cleanup cần được thiết kế cẩn thận.

## 4. Thứ tự trước không nhất thiết trùng thứ tự sau

Một nhầm lẫn phổ biến là:

> “Nếu A chạy trước B, thì A cũng phải chạy trước B ở phần after.”

Điều này không đúng với **cấu trúc lồng nhau**. Nếu A bao B, A có thể chạy trước B ở lúc vào, nhưng khi kết thúc thì B chạy phần after/finally trước A.

~~~text
A.before
  B.before
    nghiệp vụ
  B.after
A.after
~~~

Nếu đọc log mà chỉ nhìn các dòng before rồi kết luận thứ tự after phải giống như vậy, người học có thể tưởng rằng công cụ chạy sai. Thực tế, đảo chiều khi thoát là hệ quả thông thường của việc **A bao ngoài B**.

Nên phân biệt hai định nghĩa về ưu tiên:

- **Thứ tự vào (entry/outer precedence):** A ở ngoài B nên mã trước trong A chạy sớm hơn B.
- **Thứ tự thoát (exit/unwind order):** A nhận kết quả sau khi B đã hoàn thành phần hậu xử lý.

Một số mô hình AOP định nghĩa quan hệ ưu tiên theo kiểu **lớp nào có precedence cao hơn sẽ bao ngoài**; các mô hình khác có thể đặt quy tắc cụ thể cho từng loại advice. Chỉ khi biết chính xác mô hình của nền tảng mới kết luận thứ tự từng phần.

## 5. Ví dụ Java 17 chạy độc lập: ba lớp advice

Chương trình sau **tự tổ chức các lớp bọc bằng Java** nhằm mô phỏng *ngữ nghĩa nhiều around advice* mà không cần một thư viện AOP cụ thể. Nó minh họa:

- Thứ tự đi vào `SEC → TX → LOG`.
- Thứ tự đi ra `LOG → TX → SEC`.
- Sự khác nhau giữa đường thành công và đường ném ngoại lệ.
- `finally` của từng lớp vẫn chạy khi phần nằm trong nó ném lỗi.

Lưu thành file `AdviceOrderDemo.java`:

~~~java
public class AdviceOrderDemo {
    @FunctionalInterface
    interface Action {
        String call() throws Exception;
    }

    static Action layer(String name, Action next) {
        return () -> {
            System.out.println(name + " BEFORE");
            try {
                String result = next.call();
                System.out.println(name + " SUCCESS " + result);
                return result;
            } catch (Exception error) {
                System.out.println(name + " ERROR "
                        + error.getClass().getSimpleName());
                throw error;
            } finally {
                System.out.println(name + " FINALLY");
            }
        };
    }

    static String perform(String value) {
        System.out.println("BUSINESS " + value);
        if ("bad".equals(value)) {
            throw new IllegalArgumentException("bad request");
        }
        return "ok:" + value;
    }

    static void run(String value) {
        System.out.println("CASE " + value);

        Action business = () -> perform(value);
        Action withLog = layer("LOG", business);
        Action withTransaction = layer("TX", withLog);
        Action withSecurity = layer("SEC", withTransaction);

        try {
            System.out.println("RESULT " + withSecurity.call());
        } catch (Exception ex) {
            System.out.println("CALLER " + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        run("good");
        run("bad");
    }
}
~~~

Biên dịch và chạy bằng Java 17+:

~~~bash
javac AdviceOrderDemo.java
java AdviceOrderDemo
~~~

Stdout chính xác theo đoạn mã:

~~~text
CASE good
SEC BEFORE
TX BEFORE
LOG BEFORE
BUSINESS good
LOG SUCCESS ok:good
LOG FINALLY
TX SUCCESS ok:good
TX FINALLY
SEC SUCCESS ok:good
SEC FINALLY
RESULT ok:good
CASE bad
SEC BEFORE
TX BEFORE
LOG BEFORE
BUSINESS bad
LOG ERROR IllegalArgumentException
LOG FINALLY
TX ERROR IllegalArgumentException
TX FINALLY
SEC ERROR IllegalArgumentException
SEC FINALLY
CALLER bad request
~~~

### 5.1 Vì sao thứ tự ra lại đảo chiều?

Trong `run`, `layer("LOG", business)` là lớp trong cùng; `layer("TX", withLog)` bọc ngoài nó; và `layer("SEC", withTransaction)` là lớp ngoài cùng. Gọi `withSecurity.call()` thực hiện:

1. In `SEC BEFORE`.
2. Gọi tiếp vào `TX`, in `TX BEFORE`.
3. Gọi tiếp vào `LOG`, in `LOG BEFORE`.
4. Gọi phần `business`.
5. Phần `LOG` nhận kết quả hoặc lỗi, chạy khối `finally`.
6. Phần `TX` nhận kết quả hoặc lỗi từ `LOG`, chạy `finally`.
7. Phần `SEC` nhận kết quả hoặc lỗi từ `TX`, chạy `finally`.

Đây là **ngăn xếp các lời gọi**. Khi xảy ra ngoại lệ, các `catch` và `finally` tương ứng được xử lý từ phạm vi trong ra ngoài, trừ khi một lớp đã bắt và biến đổi lỗi.

### 5.2 Ví dụ không có một cơ chế kiểm tra quyền hay giao dịch thật

Các tên `SEC` và `TX` chỉ đặt nhãn cho lớp bọc để người đọc nhìn thấy thứ tự. Chương trình **không xác thực quyền**, **không mở/commit/rollback giao dịch**. Muốn tạo aspect thật cho những chức năng đó phải có chính sách, tài nguyên và các ranh giới thực thi cụ thể.

Chương trình cũng không đăng ký pointcut, không tự weave bytecode và không chứng minh thứ tự mặc định của bất kỳ nền tảng AOP nào. Mô hình wrapper này minh họa rõ một **thứ tự do người thiết kế chủ động ghép**, để phân tích hành vi trước khi chuyển sang cú pháp công cụ thật.

## 6. Nếu thay thứ tự các lớp thì điều gì thay đổi?

Giả sử giữ cùng ba xử lý, nhưng đổi từ:

~~~text
SEC → TX → LOG → BUSINESS
~~~

sang:

~~~text
LOG → TX → SEC → BUSINESS
~~~

Sự khác nhau không chỉ ở thứ tự in:

- Nếu **SEC ở ngoài cùng** và có thể từ chối trước khi gọi tiếp, yêu cầu không hợp lệ có thể dừng **trước khi TX mở giao dịch**.
- Nếu **TX ở ngoài SEC**, tài nguyên giao dịch có thể được mở rồi mới bị từ chối, dẫn đến chi phí và nhánh rollback/cleanup phát sinh sớm hơn.
- Nếu **LOG ở ngoài SEC**, một số lần từ chối có thể được ghi log từ lớp ngoài (nếu lớp log xử lý được lỗi trả về).
- Nếu **LOG ở trong SEC**, khi SEC từ chối và **không gọi tiếp**, LOG bên trong có thể **không chạy**, nên bộ đếm nằm trong LOG có thể không thấy các lần từ chối.
- Nếu advice đo thời gian nằm **ngoài TX**, phép đo có thể gồm cả thời gian mở/đóng giao dịch; nằm **trong TX** thì phạm vi đo hẹp hơn.

Một thiết kế cần nói rõ **muốn tính những hoạt động nào vào phép đo/log** và **muốn lớp nào có quyền từ chối trước lớp nào**. Thứ tự chỉ có thể được đánh giá là đúng khi gắn với mục tiêu nghiệp vụ và vận hành.

## 7. Before/after riêng rẽ và around không thể gộp máy móc

Trong mô hình wrapper, `before`, `after-success`, `after-error` và `finally` chỉ là các điểm mã nằm trước/sau lệnh gọi tiếp. Nhưng trong một hệ thống AOP thật, chúng có thể là những **advice độc lập** với quy tắc ưu tiên khác nhau.

Ví dụ diễn tả mong muốn:

~~~text
Before(Security)
Before(Audit)
Execution(Business)
AfterReturning(Audit)
AfterFinally(Security)
~~~

Đây là **một trình tự mong muốn**, không phải cú pháp/đầu ra mặc định. Ta chưa thể biết nó có đúng với công cụ đang dùng hay không cho tới khi xác nhận:

1. Security và Audit có cùng khớp điểm đang xét?
2. Cơ chế có hỗ trợ before, after returning, finally tại loại join point đó?
3. Có khai báo precedence hay thứ tự advice nào được công cụ hỗ trợ?
4. Thứ tự áp dụng giữa **các aspect khác nhau** và **nhiều advice trong cùng một aspect** có được định nghĩa riêng không?
5. Nếu cùng độ ưu tiên hoặc thiếu quan hệ precedence, hành vi có xác định không?

**Đừng suy thứ tự chạy chỉ từ thứ tự dòng source code, thứ tự định nghĩa aspect, thứ tự tên file hoặc thứ tự liệt kê trong Reflection.** Chỉ khi hợp đồng công cụ nêu rõ chúng mới có thể được dùng làm quy tắc.

## 8. Cách chỉ định thứ tự khi nền tảng có hỗ trợ

Các mô hình AOP có thể cung cấp cơ chế **priority**, **precedence**, **ordering**, hoặc quan hệ **trước–sau** giữa aspect/advice. Tên cú pháp và cách diễn giải khác nhau, nên ví dụ dưới dùng giả mã ý định:

~~~text
outermost: Security
next:      Transaction
innermost: Observability

effective nesting:
Security( Transaction( Observability( Business ) ) )
~~~

Trình tự này thể hiện thứ tự **lồng nhau**. Nếu một nền tảng dùng số thứ tự, phải đọc kỹ **số lớn hay nhỏ có ưu tiên cao**. Nếu dùng danh sách hoặc quan hệ thứ tự, phải đọc xem nó điều khiển **entry order**, **precedence**, **execution order của before**, hay một ý nghĩa riêng.

### 8.1 Quan hệ thứ tự bộ phận và những trường hợp đồng mức

Không phải mọi mối quan tâm đều cần một thứ tự tổng quát. Ví dụ có thể chỉ bắt buộc `Security` bao ngoài `Transaction`, còn một aspect đo lường độc lập có thể đặt ngoài cả hai hoặc trong tùy mục tiêu. Khi không định nghĩa đầy đủ các quan hệ liên quan, nền tảng có thể có cơ chế tie-break riêng hoặc không bảo đảm thứ tự.

Vì vậy nên thiết kế **những quan hệ thứ tự thật sự có ý nghĩa**, và kiểm thử nơi còn khả năng thay đổi.

### 8.2 Tránh yêu cầu vòng mâu thuẫn

Các quy tắc như `A trước B`, `B trước C`, nhưng `C trước A` tạo ra chu trình. Một thứ tự tuyến tính không thể thỏa cả ba. Hệ thống có thể phát hiện lỗi, từ chối cấu hình hoặc áp dụng quy tắc khác; không nên tự suy kết quả. Khi thứ tự aspect ngày càng nhiều, nên vẽ đồ thị phụ thuộc để tránh mâu thuẫn.

### 8.3 Thứ tự ổn định khi thay đổi mã

Thêm một aspect mới có thể làm thay đổi thứ tự có hiệu lực tại một join point, ngay cả khi mã nghiệp vụ không đổi. Các bài kiểm thử nên kiểm tra **quan hệ chức năng quan trọng** thay vì chỉ so sánh một tập tên advice. Ví dụ: “quyền được kiểm tra trước khi tạo tác dụng phụ” quan trọng hơn “Security có số ưu tiên 10”.

## 9. Nhiều advice của cùng một aspect

Một aspect có thể chứa nhiều advice, thậm chí nhiều advice cùng thuộc một loại (ví dụ hai before). Không nên mặc định thứ tự nguồn khai báo của chúng là thứ tự chạy.

Có thể gặp các tình huống:

- Mô hình công bố thứ tự trong cùng aspect riêng với thứ tự giữa các aspect.
- Mô hình cho phép sắp xếp rõ nhiều advice.
- Thứ tự khi đồng hạng không được bảo đảm, hoặc phụ thuộc cách weaving.
- Một advice khớp ở call join point, advice khác khớp ở execution join point: trông như cùng một thao tác nghiệp vụ nhưng thực ra tác động tại **hai điểm nối khác nhau**.

Nếu hai advice phải nối tiếp có phụ thuộc dữ liệu chặt chẽ, chẳng hạn bước B buộc phải đọc trạng thái do A vừa khởi tạo, đôi khi **gom chúng thành một advice với thứ tự nội bộ rõ ràng** dễ duy trì hơn việc dựa vào thứ tự tình cờ giữa hai advice độc lập.

Trường hợp mã xử lý cần logic cụ thể theo trạng thái kết quả, cân nhắc gom nó vào một cấu trúc `try/catch/finally` rõ ràng nếu mô hình hiện tại không đưa ra bảo đảm về thứ tự.

## 10. Các kịch bản làm thứ tự thay đổi luồng thực thi

### 10.1 Before advice ném lỗi hoặc chặn tiếp tục

Một before advice có thể phát hiện dữ liệu sai hoặc không đủ quyền rồi ném ngoại lệ. Khi đó:

- Nghiệp vụ chưa chắc được chạy.
- Những advice nằm **sau điểm từ chối trên đường đi vào** có thể chưa chạy.
- Các lớp bao ngoài có xử lý lỗi/finally có thể vẫn quan sát được việc từ chối.
- Không được giả định một `after returning` liên quan đến nghiệp vụ sẽ chạy khi nghiệp vụ chưa thực sự diễn ra.

Mục tiêu kiểm soát quyền thường yêu cầu việc từ chối diễn ra **trước tác dụng phụ cần bảo vệ**, và mọi lối vào thích hợp đều chịu kiểm tra. Thứ tự advice không thay thế việc xác định đúng phạm vi join point.

### 10.2 Around advice bỏ qua `proceed`

Một around advice có thể quyết định không gọi tiếp (nếu cơ chế cho phép). Khi đó các lớp bên trong và nghiệp vụ không chạy. Điều này có thể được dùng cho caching, circuit breaking hoặc một chính sách bỏ qua có chủ đích, nhưng phải tuân thủ hợp đồng phương thức và không vô tình bỏ qua kiểm tra bắt buộc.

Nếu lớp cache nằm **ngoài** kiểm tra quyền và trả cache hit mà không gọi tiếp, lớp kiểm tra quyền bên trong sẽ không chạy. Thiết kế đó có thể tạo lỗ hổng nếu dữ liệu cache phải được bảo vệ theo người dùng. Vì vậy cần phân tích rõ **lớp nào có thể short-circuit lớp nào**.

### 10.3 Around advice gọi tiếp nhiều lần

Khi cơ chế cho phép gọi `proceed` nhiều lần, các advice bên trong và nghiệp vụ có thể thực thi nhiều lần. Điều này có thể hợp lệ cho retry, nhưng có thể tạo tác dụng phụ lặp lại: thanh toán hai lần, tăng counter hai lần hoặc gửi thông báo trùng.

Một lớp đo lường ở ngoài retry có thể đếm **một yêu cầu logic**, còn lớp ở trong có thể đếm **nhiều lần thử**. Hai phép đo đều có thể đúng, nhưng đơn vị đo khác nhau. Cần ghi rõ tên metrics: `requests` khác `attempts`.

### 10.4 Advice chuyển đổi ngoại lệ

Giả sử nghiệp vụ ném `IOException`, inner advice bắt rồi trả một đối tượng kết quả thất bại thay vì ném tiếp. Khi đó:

- Inner advice có thể đi qua nhánh lỗi rồi chuyển thành giá trị bình thường.
- Outer advice có thể nhìn thấy **lần gọi trả về bình thường**, chạy xử lý success.
- Một transaction wrapper bên ngoài có thể hiểu đây là thành công nếu nó chỉ rollback khi có ngoại lệ.

Vì vậy, khi gắn advice với giao dịch, **không được chỉ dựa vào tên after-error**. Cần biết một lớp có thể nuốt lỗi, đổi loại lỗi hoặc trả dữ liệu thất bại dưới dạng giá trị thường hay không.

### 10.5 Advice tự ném ngoại lệ trong phần after/finally

Một lỗi phát sinh **sau khi nghiệp vụ thành công** trong inner advice có thể khiến outer advice nhìn thấy lỗi. Ngược lại, một lỗi trong `finally` có thể che mất ngoại lệ gốc. Hệ thống ghi log/metrics và cleanup nên hạn chế các tác dụng phụ gây lỗi, có chính sách rõ việc giữ và báo lỗi thứ cấp, tránh làm sai hợp đồng nghiệp vụ.

## 11. Quan sát log và trace không được suy thành thứ tự nghiệp vụ

Một hệ thống có nhiều luồng, tác vụ bất đồng bộ và bộ ghi log không đồng bộ có thể hiển thị dòng log theo thứ tự khác với **quan hệ happens-before** của một chuỗi xử lý cụ thể. Ngay cả khi wrapper chạy đúng thứ tự, việc lưu/truyền log sang hệ thống ngoài có thể được xếp lịch độc lập.

Do đó:

- Dùng **correlation ID** hoặc trace ID để nhóm các sự kiện thuộc cùng lần chạy.
- Khi cần chứng minh thứ tự advice, ghi sự kiện trực tiếp vào một danh sách tuần tự trong một phép thử đồng bộ, thay vì suy từ log của nhiều thread.
- Phân biệt thứ tự **bắt đầu xử lý**, thứ tự **kết thúc callback**, và thứ tự **dữ liệu hiện ra trên hệ thống log**.
- Không cho rằng after returning của phương thức trả về `Future`/`CompletionStage` có nghĩa công việc bất đồng bộ đã hoàn tất. Advice sau-return có thể chỉ chạy khi phương thức **trả về đối tượng đại diện kết quả**, trước khi tác vụ hoàn tất. Muốn xử lý lúc hoàn tất cần móc đúng tín hiệu hoàn thành theo cơ chế phù hợp.
- Không mặc định context gắn với thread tự truyền qua mọi thread hoặc tác vụ nền.

### 11.1 Đo thời gian đặt ở lớp nào?

~~~text
METRICS(
    SECURITY(
        TRANSACTION(
            BUSINESS
        )
    )
)
~~~

Nếu metrics bao ngoài tất cả, thời gian đo có thể bao gồm kiểm tra quyền và xử lý giao dịch. Nếu metrics đặt ngay quanh business, nó có thể **không tính** phần đó. Lúc yêu cầu bị từ chối trước business, metrics bên trong business không chạy, còn metrics bên ngoài có thể ghi độ trễ từ chối. Phạm vi đo cần được **đặt tên chính xác**, không gọi mọi thời gian đo là “thời gian nghiệp vụ”.

## 12. Hệ quả của pointcut và nhiều join point

Một method call thường dẫn tới một method execution, nhưng không thể luôn coi chúng là **một join point**. Nếu một aspect chọn **call** còn một aspect khác chọn **execution**, cả hai có thể tác động trên cùng thao tác ở hai vị trí khác nhau.

~~~text
Caller
  |
  +--> call advice
          |
          +--> execution advice
                  |
                  +--> method body
~~~

Sơ đồ chỉ là trường hợp khái niệm đơn giản. Sự có mặt và thứ tự thực tế phụ thuộc weaving, dispatch, loại lời gọi và những điểm mà mô hình hỗ trợ.

Các ví dụ dễ gây bất ngờ:

- Một lời gọi đến nhiều phương thức lồng nhau làm sinh thêm nhiều execution join point.
- Một advice ghi log gọi helper; helper lại thỏa pointcut, gây **tự can thiệp/đệ quy advice**.
- Proxy chỉ chặn lời gọi qua proxy; self-invocation trên đối tượng gốc có thể bỏ qua advice proxy.
- Bridge/synthetic methods hoặc mã sinh có thể xuất hiện trong class file, nhưng một bộ AOP có thể bỏ qua chúng hoặc có quy tắc khác. Không mặc định mọi phương thức có trong Reflection đều tạo execution advice.
- Constructor, field access, exception handler và các điểm đặc biệt khác chỉ có khi mô hình AOP hỗ trợ chúng.

Một kết luận đúng về thứ tự tại **cùng một điểm và cùng một tập advice** không tự động áp dụng cho các chuỗi điểm nối khác nhau.

## 13. Xử lý nhiều aspect: thiết kế theo bất biến thay vì tên gọi

### 13.1 Bảo mật và tài nguyên giao dịch

Bất biến cần giữ: *một yêu cầu bị từ chối không được thực hiện tác dụng phụ được bảo vệ*. Từ đó suy ra cần kiểm tra quyền tại điểm đủ sớm và không bị bỏ qua bởi cache, retry hoặc proxy bypass.

Thứ tự mở giao dịch trước/sau kiểm tra quyền tùy mục đích và hợp đồng, nhưng thông thường muốn tránh khởi tạo tài nguyên không cần thiết trước khi biết yêu cầu được phép xử lý. Tuy nhiên, nếu bản thân quá trình kiểm tra quyền yêu cầu một ngữ cảnh giao dịch nhất quán, cần thiết kế ranh giới riêng; không nên áp đặt một thứ tự duy nhất cho mọi hệ thống.

### 13.2 Giao dịch và retry

Nếu retry nằm **ngoài transaction**, mỗi lần thử có thể được thực hiện trong giao dịch riêng, nếu cơ chế và cách cấu hình thực sự tạo giao dịch mới cho mỗi attempt. Nếu retry ở **trong cùng một transaction**, nhiều lần thử có thể chia sẻ trạng thái đã bị lỗi, dẫn đến hành vi khác.

Điều quan trọng là **xác định ranh giới giao dịch và ranh giới lần thử**, không đơn giản chỉ ghi “Retry ưu tiên cao hơn Transaction”. Các lỗi chỉ định rollback, cách đánh dấu transaction không dùng được và tính idempotent của nghiệp vụ phải được xử lý theo hợp đồng thật.

### 13.3 Ghi log và bảo mật dữ liệu

Đặt logging ngoài kiểm tra quyền có thể giúp quan sát từ chối, nhưng cũng có thể vô tình ghi dữ liệu chưa được phép công bố. Đặt logging trong lớp kiểm tra quyền có thể bảo vệ dữ liệu tốt hơn, nhưng mất sự kiện từ chối. Có thể thiết kế **audit từ chối** với dữ liệu tối thiểu ở phạm vi ngoài và **log nghiệp vụ** ở phạm vi sau xác thực, thay vì cố dùng một advice duy nhất cho mọi nhu cầu.

## 14. Kiểm thử thứ tự advice

Không nên chỉ kiểm tra “mỗi advice đều đã chạy”. Phải kiểm tra cả **thứ tự, số lần, nhánh và tác dụng quan sát được**.

| Kịch bản | Điều cần kiểm chứng |
| --- | --- |
| Nghiệp vụ thành công | Các lớp vào và ra theo thứ tự kỳ vọng; kết quả không bị thay đổi trái ý |
| Nghiệp vụ ném lỗi | Nhánh error/finally đúng; ngoại lệ được truyền tiếp hoặc chuyển đổi theo hợp đồng |
| Before chặn | Những lớp bên trong không chạy; cleanup lớp ngoài thực hiện nếu cần |
| Around không gọi tiếp | Không tự giả định nghiệp vụ/advice bên trong đã chạy |
| Retry gọi tiếp nhiều lần | Đếm đúng số attempt và số request logic |
| Inner nuốt lỗi | Outer nhìn đúng tín hiệu success hoặc trạng thái lỗi đã chuyển đổi |
| After/finally ném lỗi | Không vô tình che lỗi ban đầu ngoài chính sách |
| Hai advice đồng ưu tiên | Nếu nền tảng không bảo đảm thứ tự, không đặt bất biến phụ thuộc vào thứ tự đó |
| Nhiều join point | Biết đây là call hay execution và phạm vi weave có bao phủ tất cả đường gọi không |
| Bất đồng bộ | Phân biệt lúc trả về handle và lúc hoàn thành thật |
| Thay thứ tự | Quan sát sự khác biệt đúng mục đích về transaction, security, logging hoặc timing |

Một kỹ thuật hữu ích là kiểm thử bằng **danh sách sự kiện tuần tự**:

~~~text
expected = [
  "SEC.before",
  "TX.before",
  "LOG.before",
  "BUSINESS",
  "LOG.success",
  "LOG.finally",
  "TX.success",
  "TX.finally",
  "SEC.success",
  "SEC.finally"
]
~~~

Đây là dạng dữ liệu giả mã phục vụ assertion, không phải cú pháp của một bộ AOP cụ thể. Danh sách này tương ứng với **mô hình lồng nhau đã chọn** và nhánh thành công; với hệ thống khác phải tạo expected theo hợp đồng thực tế.

Để tránh kiểm thử giòn, nên phân biệt **ràng buộc thứ tự bắt buộc** (ví dụ Security trước tác dụng phụ) với thứ tự không quan trọng (ví dụ hai phép đo độc lập). Nếu thứ tự hai advice đồng mức không được định nghĩa, hãy tách chúng hoặc cấu hình precedence rõ ràng thay vì phụ thuộc vào kết quả tình cờ của một lần chạy.

## 15. Các lỗi hiểu sai phổ biến

1. **“Advice khai báo đầu tiên luôn chạy trước.”** Không có quy tắc chung như vậy; phải đọc hợp đồng ordering/precedence của nền tảng.
2. **“Before nào chạy trước thì after của nó cũng chạy trước.”** Không đúng với lớp bọc lồng nhau, vì phần ra thường đảo chiều.
3. **“After chạy ngay cả khi lỗi.”** Phải phân biệt after-success, after-error và finally.
4. **“Có nhiều advice nên tất cả đều chắc chắn chạy.”** Before có thể ném lỗi, around có thể không gọi tiếp hoặc điểm không được weave.
5. **“Chỉ cần sắp xếp là bảo đảm kiểm soát quyền.”** Nếu pointcut không bao phủ đường vào hoặc advice bị short-circuit từ bên ngoài, thứ tự không đủ bảo vệ.
6. **“Outer advice luôn thấy lỗi nguyên gốc.”** Inner advice có thể chuyển đổi, nuốt hoặc thay ngoại lệ.
7. **“Chạy một lần phương thức tức mỗi advice chạy đúng một lần.”** Retry, multiple join points, bridge/proxy hoặc một cơ chế weave cụ thể có thể tạo các số lần khác nhau.
8. **“Log ra theo thứ tự này chứng minh mọi thread đều chạy vậy.”** Bản thân log và xử lý bất đồng bộ có thể ảnh hưởng thứ tự hiển thị.
9. **“Số thứ tự nhỏ luôn có ưu tiên cao hơn.”** Quy ước số và ý nghĩa priority phụ thuộc mô hình; không được đoán.
10. **“Chỉ có một thứ tự đúng cho Security–Transaction–Logging.”** Thứ tự phải được thiết kế từ các bất biến cụ thể và phạm vi quan sát/chi phí mong muốn.

## 16. Bài tập tự kiểm tra

### Bài 1: Thứ tự bọc

Cho ba lớp `A(B(C(Business)))`, mỗi lớp in `before`, sau đó gọi lớp trong, in `success` khi trả về và `finally` ở mọi nhánh.

Nếu nghiệp vụ thành công, thứ tự nào là đúng?

**Đáp:** `A.before → B.before → C.before → Business → C.success → C.finally → B.success → B.finally → A.success → A.finally`.

### Bài 2: Chặn từ lớp ngoài

Vẫn cấu trúc trên, nhưng `A` phát hiện không đủ quyền rồi ném ngoại lệ **trước khi gọi B**. Có thể khẳng định `B.before`, `C.before` và `Business` chạy không?

**Đáp:** không. Chúng không được gọi trong đường xử lý này. Những xử lý catch/finally của phạm vi *đã được vào* có thể chạy theo cách được tổ chức. Cần thiết kế logging từ chối ở một phạm vi thực sự nhìn thấy lỗi đó.

### Bài 3: Lỗi bị chuyển thành thành công

`C` bắt ngoại lệ từ nghiệp vụ rồi trả giá trị dự phòng. `B` và `A` có bắt buộc chạy nhánh after-error không?

**Đáp:** không. Nếu chúng nhận một giá trị bình thường từ C, chúng có thể chạy nhánh success. Vì vậy không được phụ thuộc đơn độc vào ngoại lệ để rollback khi một lớp bên trong có thể chuyển đổi lỗi.

### Bài 4: Đo latency

Muốn đo toàn bộ thời gian từ khi yêu cầu vào lớp kiểm tra quyền đến khi trả kết quả. Nên đặt lớp đo thời gian ngoài hay trong lớp kiểm tra quyền?

**Đáp:** đặt bao ngoài phạm vi cần đo để phép đo bao gồm phần đó; sau đó xác minh cả nhánh từ chối. Nếu chỉ muốn đo phần nghiệp vụ, đặt trong phạm vi đã qua kiểm tra. Không có “vị trí tốt nhất” khi chưa xác định đại lượng.

### Bài 5: Hai loại điểm nối

Một advice chọn method call, advice khác chọn method execution của cùng phương thức. Có thể lấy cùng quy tắc precedence giữa hai advice ở *một join point* để chắc chắn toàn bộ chương trình có thứ tự giống nhau không?

**Đáp:** không thể suy như vậy. Đó là hai loại điểm nối và có thể xảy ra ở hai vị trí khác nhau. Cần hiểu cơ chế weave và đường gọi thực tế.

## 17. Checklist áp dụng thực tế

Khi một nhóm dự định thêm aspect mới vào hệ thống đang có nhiều advice, nên ghi nhận:

- **Các join point thật sự liên quan**, pointcut nào khớp ở mỗi điểm.
- **Loại advice** (before, after-success, after-error, finally, around) và khả năng tiếp tục/chặn/đổi lỗi.
- **Quan hệ bao ngoài–bên trong** mong muốn; thứ tự lúc vào và lúc thoát.
- **Bất biến bắt buộc:** xác thực trước tác dụng phụ, rollback khi cần, cleanup không rò tài nguyên, không đếm trùng.
- **Cấu hình ordering theo nền tảng:** quy tắc ưu tiên, tie-break, trường hợp mâu thuẫn, khác biệt giữa nhiều aspect và advice trong một aspect.
- **Nhánh biên:** ngoại lệ, retry, cache hit, short-circuit, bất đồng bộ, self-invocation và phương thức không thuộc phạm vi weaving.
- **Bài kiểm thử thứ tự:** một vài trace mong đợi rõ ràng trên các trường hợp thành công, từ chối và lỗi, cộng với kiểm thử tính đúng đắn nghiệp vụ.

**Kết luận:** Trong mô hình nhiều lớp can thiệp, thứ tự advice phải được hiểu như **một quan hệ bao ngoài–bên trong có thể thay đổi luồng điều khiển**, chứ không chỉ là thứ tự khai báo. Với lớp bọc lồng nhau, xử lý trước thường đi **ngoài → trong**, còn xử lý sau/tháo ngăn xếp thường đi **trong → ngoài**. Tuy nhiên, cách xác định thứ tự, nhóm advice và join point phụ thuộc nền tảng AOP; thiết kế đúng phải dựa trên hợp đồng cụ thể, nhánh thành công/lỗi và các bất biến nghiệp vụ được kiểm thử.
