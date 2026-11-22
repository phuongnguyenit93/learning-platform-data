# Phân biệt điều kiện bao gồm với điều kiện loại trừ trong pointcut AOP

> **Mục tiêu học tập:** Hiểu điều kiện **bao gồm** (*inclusion*) xác định phạm vi join point ứng viên mà một chính sách AOP muốn áp dụng, còn điều kiện **loại trừ** (*exclusion*) gỡ khỏi phạm vi đó những điểm không nên được áp dụng. Biết diễn đạt bằng logic tập hợp, kết hợp AND/OR/NOT, xử lý quy tắc chồng lấn, kiểm thử trường hợp biên và phân biệt một điểm bị loại với điểm vốn không được công cụ AOP hỗ trợ.

## 1. Vấn đề: “áp dụng ở đâu?” và “trừ những đâu?”

Giả sử một ứng dụng có nhiều thao tác xử lý đơn hàng. Ta cần đo thời gian những phương thức **gửi đơn hàng**, nhưng không muốn đo các thao tác **kiểm thử nội bộ** hoặc các lời gọi xuất phát từ một luồng tác vụ có mục đích khác.

Có thể mô tả chính sách như sau:

> **Bao gồm:** các điểm thực thi phương thức gửi đơn hàng. **Loại trừ:** điểm gửi đơn thuộc môi trường kiểm thử hoặc thao tác nội bộ không cần đo.

Hai vế phục vụ các câu hỏi khác nhau:

- **Điều kiện bao gồm** xác định: *“Những điểm nào là ứng viên cho chính sách?”*
- **Điều kiện loại trừ** xác định: *“Trong số các ứng viên đó, những điểm nào phải bỏ qua?”*

Một pointcut có thể biểu đạt cả hai bằng cách kết hợp điều kiện. Nếu viết thiếu vế bao gồm, phạm vi có thể quá rộng; nếu viết thiếu ngoại lệ loại trừ, advice có thể chạy ở những chỗ không mong muốn. Ngược lại, loại trừ quá nhiều có thể khiến chính sách mất độ bao phủ quan trọng.

**Pointcut** chỉ xác định tập điểm được chọn. Nó không tự quyết định hành vi advice là ghi log, đo thời gian hay kiểm toán; những hành vi đó thuộc một thành phần khác trong mô hình lập trình hướng khía cạnh (Aspect-Oriented Programming, AOP).

## 2. Ôn lại bốn thành phần liên quan

| Thành phần | Trách nhiệm | Ví dụ |
|---|---|---|
| **Join point** | Một điểm/sự kiện thực thi mà mô hình AOP có thể nhận diện | Một lần thực thi `submitOrder(...)` |
| **Pointcut** | Điều kiện lọc các join point | Chọn `submitOrder` trừ một số ngữ cảnh |
| **Advice** | Hành vi chạy tại các điểm được chọn | Ghi thời gian và kết quả |
| **Aspect** | Mô-đun hóa pointcut và advice cho mối quan tâm xuyên suốt | Khía cạnh đo lường thao tác đơn hàng |

Một hoạt động có thật trong chương trình không nhất thiết là join point được công cụ đang dùng hỗ trợ. Pointcut **chỉ lọc** những điểm nằm trong mô hình join point của công cụ. Sau đó, mức độ bao phủ thực tế còn phụ thuộc phạm vi weaving và đường thực thi.

Trong bài này, trước hết ta giả định có một **tập join point ứng viên hợp lệ** để hiểu logic bao gồm và loại trừ. Phần sau sẽ tách riêng những giới hạn khi đi từ lý thuyết sang thực thi.

## 3. Biểu thức cốt lõi: bao gồm VÀ không thuộc loại trừ

Ký hiệu:

- `J`: tập join point mà mô hình AOP có thể xem xét trong phạm vi đang xét.
- `I(j)`: điều kiện **bao gồm** tại join point `j`.
- `E(j)`: điều kiện **loại trừ** tại join point `j`.
- `P(j)`: kết quả pointcut cuối cùng.

Công thức thông dụng:

```text
P(j) = I(j) AND NOT E(j)
```

Hoặc dưới dạng tập hợp:

```text
Include = { j thuộc J | I(j) đúng }
Exclude = { j thuộc J | E(j) đúng }

Matched = Include \ Exclude
        = Include ∩ (J \ Exclude)
```

Cách đọc: bắt đầu bằng tất cả điểm thuộc **Include**, sau đó **bỏ** những điểm đồng thời thuộc **Exclude**. Một điểm chỉ được chọn khi nó **được bao gồm** và **không bị loại trừ**.

### 3.1. Bảng chân trị

| Bao gồm I | Loại trừ E | I AND NOT E | Quyết định |
|---|---|---|---|
| Sai | Sai | Sai | Không chọn: vốn không thuộc miền được bao gồm |
| Sai | Đúng | Sai | Không chọn: điều kiện bao gồm vẫn không thỏa |
| Đúng | Sai | **Đúng** | **Chọn** |
| Đúng | Đúng | Sai | Không chọn: bị ngoại lệ loại bỏ |

Hàng cuối rất quan trọng: **một join point khớp điều kiện bao gồm chưa chắc được chọn cuối cùng**. Nếu đồng thời khớp điều kiện loại trừ, nó bị loại.

Hàng thứ hai cũng có ý nghĩa: loại trừ một điểm vốn không thuộc Include **không làm thay đổi** tập Matched. Điều kiện loại trừ không cần thiết phải là tập con của Include để biểu thức có nghĩa, nhưng một phần Exclude ở ngoài Include sẽ không ảnh hưởng tới kết quả hiện tại.

### 3.2. Hình dung hai bước lọc

```text
Tập join point trong phạm vi mô hình J
                    |
                    v
           Điều kiện bao gồm I
                    |
                    v
          Tập ứng viên Include
                    |
                    v
      Bỏ những điểm thỏa E (NOT E)
                    |
                    v
              Matched
                    |
                    v
       Advice áp dụng ở điểm phù hợp
```

Sơ đồ mang ý nghĩa **logic**, không bắt buộc mô tả thứ tự đánh giá vật lý của mọi bộ máy AOP. Công cụ có thể tối ưu, phân tích phần cấu trúc trước, rút gọn hoặc đánh giá điều kiện động tại thời điểm chạy.

## 4. Điều kiện bao gồm thường có dạng nào?

Điều kiện bao gồm xác định **phạm vi có chủ đích** của mối quan tâm xuyên suốt. Một số tiêu chí mà các mô hình AOP có thể hỗ trợ là:

- **Loại join point:** thực thi phương thức, vị trí gọi phương thức, thực thi constructor, truy cập trường… nếu mô hình hỗ trợ.
- **Phạm vi mã:** lớp, nhóm kiểu, gói, thành phần hoặc mô-đun.
- **Tên/chữ ký:** tên phương thức, kiểu tham số, kiểu trả về hoặc đặc điểm khai báo.
- **Metadata:** dấu hiệu khai báo, chẳng hạn annotation, nếu công cụ đọc được.
- **Ngữ cảnh động:** kiểu/giá trị đối số, đối tượng liên quan hoặc trạng thái luồng điều khiển, nếu được hỗ trợ.

Ví dụ diễn đạt độc lập công cụ:

```text
I = METHOD_EXECUTION
    AND module = "orders"
    AND methodName STARTS_WITH "submit"
```

Ta chỉ quan tâm đến **các điểm thực thi phương thức gửi đơn ở mô-đun orders**. Nếu có method `cancelOrder()`, dù xảy ra cùng mô-đun, nó không thuộc Include. Nếu có `submitReport()` ở mô-đun reports, nó cũng không thuộc Include.

**Không nên dùng điều kiện bao gồm “mọi method” nếu yêu cầu thật sự chỉ liên quan một nhóm chức năng.** Phạm vi càng rộng, càng khó biết có bao nhiêu điểm ngoài dự tính được áp dụng khi hệ thống mở rộng.

## 5. Điều kiện loại trừ nhằm giải quyết vấn đề gì?

Điều kiện loại trừ là **ngoại lệ có chủ đích** đối với phạm vi bao gồm. Những ví dụ có giá trị:

- Bỏ qua phương thức chỉ phục vụ thao tác nội bộ không cần quan sát.
- Bỏ qua thao tác thuộc một chế độ thử nghiệm có phạm vi đo riêng.
- Bỏ qua nhóm phương thức tần suất cao, nơi advice gây chi phí vượt lợi ích.
- Bỏ qua điểm có cơ chế xử lý riêng nhằm tránh ghi trùng.
- Bỏ qua hoạt động mà dữ liệu không nên đi vào chính sách ghi nhận.

Ví dụ:

```text
E = isInternalOperation
    OR tier = "TEST"
```

Kết hợp:

```text
P = I AND NOT E
  = I AND NOT (isInternalOperation OR tier = "TEST")
```

Điểm cần chú ý: đây là **hai điều kiện loại trừ** nối bằng OR, nên chỉ cần **một trong hai đúng** là điểm bị loại. Nếu dùng AND bên trong E:

```text
E = isInternalOperation AND tier = "TEST"
```

thì chỉ loại trường hợp **vừa nội bộ vừa thuộc TEST**; nhiều điểm mà người viết định loại có thể vẫn được chọn. Phải đọc đúng từng toán tử, không chỉ hiểu chung chung “có phủ định”.

## 6. Bao gồm không đồng nghĩa với “mọi thứ không bị loại trừ”

So sánh:

```text
P1 = includeOrders AND NOT excludeTests
P2 = NOT excludeTests
```

Hai biểu thức **không tương đương**. `P1` chỉ chọn nhóm orders không bị loại. `P2` là phép phủ định trên toàn bộ **miền J mà biểu thức được đánh giá**, nên có thể chọn rất nhiều join point khác nhóm orders.

Ví dụ J gồm các lần thực thi method của orders, reports và inventory. Nếu `excludeTests` chỉ kiểm tra dấu hiệu TEST, thì `P2` có thể chọn cả reports/inventory không thuộc TEST. Trong một hệ thống lớn, đó thường là phạm vi ngoài ý định.

**Nguyên tắc thiết kế:** ưu tiên một miền bao gồm có ý nghĩa rõ, rồi thêm ngoại lệ cần thiết. Một điều kiện chỉ có `NOT E` đôi khi hợp lệ, nhưng phải chủ động chấp nhận phần bù **rất rộng** của E trên J.

### 6.1. Phép phủ định phụ thuộc miền

Trong toán học:

```text
NOT E = J \ E
```

Điều này không có nghĩa “mọi sự kiện trên thế giới trừ E”. Nó chỉ là phần bù **trong tập join point mà mô hình AOP đang xét**. Nếu công cụ không hỗ trợ field-set join point, dùng `NOT excludeFieldWrites` không biến các thao tác ghi trường thành join point mới.

Đây là điểm dễ nhầm khi dùng wildcard kết hợp phủ định.

## 7. Thứ tự ưu tiên toán tử và dấu ngoặc

Giả sử:

- `A`: điểm thuộc mô-đun orders.
- `B`: điểm thuộc mô-đun invoices.
- `E`: điểm được đánh dấu nội bộ.

Ta muốn bao gồm cả A hoặc B, **nhưng loại các điểm nội bộ ở cả hai nhóm**:

```text
P = (A OR B) AND NOT E
```

Nếu viết sai nhóm:

```text
P_wrong = A OR (B AND NOT E)
```

thì mọi điểm thuộc A vẫn được chọn dù thuộc E; chỉ B chịu điều kiện loại trừ. Hai biểu thức tạo ra kết quả khác nhau.

| A | B | E | (A OR B) AND NOT E | A OR (B AND NOT E) |
|---|---|---|---|---|
| Đúng | Sai | Đúng | **Sai** | **Đúng** |
| Sai | Đúng | Đúng | Sai | Sai |
| Đúng | Sai | Sai | Đúng | Đúng |
| Sai | Đúng | Sai | Đúng | Đúng |

Các ngôn ngữ biểu thức pointcut có thể quy định thứ tự ưu tiên khác nhau hoặc hạn chế phép toán. **Đặt dấu ngoặc tường minh** giúp thể hiện ý định và tránh phụ thuộc vào việc người đọc nhớ một quy tắc cú pháp cụ thể.

## 8. Phép kết hợp nhiều điều kiện: AND, OR, NOT

Với `I1`, `I2` là các tập bao gồm con và `E1`, `E2` là các tập loại trừ:

```text
P = (I1 OR I2) AND NOT (E1 OR E2)
```

Biểu thức trên nghĩa là:

1. Chọn ứng viên thuộc **ít nhất một** trong hai nhóm `I1`, `I2`.
2. Loại những điểm thỏa **bất kỳ** điều kiện loại trừ nào, `E1` hoặc `E2`.

Theo luật De Morgan:

```text
NOT (E1 OR E2) = (NOT E1) AND (NOT E2)
NOT (E1 AND E2) = (NOT E1) OR (NOT E2)
```

Vì vậy có thể viết tương đương về logic:

```text
P = (I1 OR I2) AND (NOT E1) AND (NOT E2)
```

Nhưng điều này chỉ bảo đảm tương đương khi các phần là **predicate logic có cùng cách đánh giá**. Nếu một cơ chế cho phép điều kiện gây tác dụng phụ hoặc có semantics lỗi/giá trị không thông thường, cần kiểm chứng riêng. Về thiết kế, nên giữ biểu thức chọn mang tính dự đoán và hạn chế tác dụng phụ.

### 8.1. Bao gồm rộng hơn có xu hướng mở rộng tập kết quả

Nếu `I1` là tập con của `I2` và Exclude giữ nguyên:

```text
(I1 \ E) ⊆ (I2 \ E)
```

Mở rộng Include không làm mất những điểm đã chọn theo mô hình tập hợp. Nó có thể làm tăng các điểm được chọn.

### 8.2. Loại trừ rộng hơn có xu hướng thu hẹp tập kết quả

Nếu `E1` là tập con của `E2` và Include giữ nguyên:

```text
(I \ E2) ⊆ (I \ E1)
```

Thêm ngoại lệ loại trừ có thể giảm độ bao phủ, nhưng không tự tăng nó. Đây là cách kiểm tra định hướng khi sửa pointcut: nếu vừa mở rộng Exclude mà số điểm khớp tăng bất thường, cần xem lại logic, cú pháp hoặc điều kiện động.

## 9. Ví dụ Java 17: lọc bao gồm/loại trừ trên tập join point giả lập

Để tập trung vào **logic lựa chọn**, chương trình sau mô hình hóa mỗi sự kiện ứng viên bằng một `record`. Nó dùng `Predicate` để thể hiện Include, Exclude và các yếu tố bao phủ. Đây là **mô phỏng bộ lọc bằng Java thuần**, không phải một công cụ weaving AOP thực sự.

Ví dụ cố ý kiểm tra thêm:

- `model`: sự kiện có thuộc **loại join point được cơ chế giả định hỗ trợ** không?
- `woven`: phần mã liên quan có được **giả định** nằm trong phạm vi can thiệp không?
- `include`: sự kiện có thuộc nhóm được chọn?
- `exclude`: sự kiện có thuộc nhóm ngoại lệ?

Lưu file `PointcutIncludeExcludeDemo.java`:

```java
import java.util.List;
import java.util.function.Predicate;

public class PointcutIncludeExcludeDemo {
    enum Kind {
        METHOD_EXECUTION,
        CONSTRUCTOR_EXECUTION
    }

    record Candidate(
            String id,
            Kind kind,
            String module,
            String action,
            boolean internal,
            String tier,
            boolean woven
    ) {}

    static String flag(boolean value) {
        return value ? "Y" : "N";
    }

    public static void main(String[] args) {
        Predicate<Candidate> model =
                c -> c.kind() == Kind.METHOD_EXECUTION;

        Predicate<Candidate> include =
                c -> "orders".equals(c.module())
                        && c.action().startsWith("submit");

        Predicate<Candidate> exclude =
                c -> c.internal() || "TEST".equals(c.tier());

        Predicate<Candidate> selected =
                model.and(include)
                        .and(exclude.negate())
                        .and(Candidate::woven);

        List<Candidate> cases = List.of(
                new Candidate("orderVIP", Kind.METHOD_EXECUTION,
                        "orders", "submitOrder", false, "VIP", true),
                new Candidate("orderTest", Kind.METHOD_EXECUTION,
                        "orders", "submitOrder", false, "TEST", true),
                new Candidate("internal", Kind.METHOD_EXECUTION,
                        "orders", "submitOrder", true, "VIP", true),
                new Candidate("cancel", Kind.METHOD_EXECUTION,
                        "orders", "cancelOrder", false, "VIP", true),
                new Candidate("constructor", Kind.CONSTRUCTOR_EXECUTION,
                        "orders", "submitOrder", false, "VIP", true),
                new Candidate("unwoven", Kind.METHOD_EXECUTION,
                        "orders", "submitOrder", false, "VIP", false)
        );

        for (Candidate c : cases) {
            System.out.printf(
                    "%s: model=%s include=%s exclude=%s woven=%s -> advice=%s%n",
                    c.id(),
                    flag(model.test(c)),
                    flag(include.test(c)),
                    flag(exclude.test(c)),
                    flag(c.woven()),
                    flag(selected.test(c))
            );
        }
    }
}
```

Chạy bằng Java 17 hoặc mới hơn:

```bash
javac PointcutIncludeExcludeDemo.java
java PointcutIncludeExcludeDemo
```

Kết quả stdout:

```text
orderVIP: model=Y include=Y exclude=N woven=Y -> advice=Y
orderTest: model=Y include=Y exclude=Y woven=Y -> advice=N
internal: model=Y include=Y exclude=Y woven=Y -> advice=N
cancel: model=Y include=N exclude=N woven=Y -> advice=N
constructor: model=N include=Y exclude=N woven=Y -> advice=N
unwoven: model=Y include=Y exclude=N woven=N -> advice=N
```

**Diễn giải:**

- **`orderVIP`** thuộc mô hình, được bao gồm, không bị loại trừ và nằm trong giả định weaving scope, nên được chọn.
- **`orderTest`** thỏa Include nhưng có tier TEST, nên Exclude đúng và không được chọn.
- **`internal`** thỏa Include nhưng là thao tác nội bộ, nên Exclude đúng và không được chọn.
- **`cancel`** không thỏa Include; không cần có ngoại lệ loại trừ vẫn không được chọn.
- **`constructor`** có thuộc tính được Include chọn theo tên/mô-đun, nhưng **khác loại join point** mà mô hình giả định hỗ trợ nên không đủ điều kiện.
- **`unwoven`** thỏa điều kiện pointcut khái niệm, nhưng bị đánh dấu ngoài phạm vi weaving nên không có advice được kích hoạt trong mô phỏng.

Hàm `selected` của ví dụ là phép kết hợp **điều kiện pointcut và điều kiện giả lập về mô hình/triển khai** để giải thích kết quả cuối. Trong một công cụ AOP thực, những ranh giới như join point model và weaving scope có thể được giải quyết bên ngoài biểu thức pointcut; chúng **không nhất thiết là những predicate người dùng phải tự viết**.

### 9.1. Sự khác nhau giữa hàm chọn và advice

Chương trình trên chỉ tính toán nhãn `advice=Y/N` để minh họa. Nó **không có aspect weaving** và không gắn hành vi vào những phương thức thật. Trong AOP, pointcut xác định điểm; advice mới là phần thực hiện việc đo thời gian, ghi vết hoặc kiểm toán khi điểm được chọn và cơ chế can thiệp được kích hoạt.

Chức năng học tập của đoạn Java là làm rõ **logic bao gồm/loại trừ** và lý do một điểm không được áp dụng. Không nên dùng việc hàm `Predicate.test()` trả true như bằng chứng một runtime AOP bất kỳ chắc chắn chạy advice.

## 10. Nhận diện sự khác nhau giữa “không bao gồm” và “bị loại trừ”

Hai trường hợp cùng dẫn đến kết quả **không chọn**, nhưng nguyên nhân và hướng sửa khác nhau.

**Không bao gồm:** `cancelOrder()` không thuộc quy tắc bao gồm `submit*`. Nếu yêu cầu thay đổi để áp dụng cả `cancelOrder`, cần **mở rộng Include** hoặc thêm một nhóm bao gồm phù hợp.

**Bị loại trừ:** `submitOrder("TEST")` đã thuộc Include nhưng bị chính sách Exclude gạt ra. Nếu cần áp dụng ở TEST, phải **thu hẹp hoặc sửa Exclude**.

Đây là sự khác biệt quan trọng trong chẩn đoán. Nếu chỉ biết “không có log”, người phát triển có thể sửa sai phần của pointcut và tạo ra vùng bao phủ ngoài ý định.

| Tình trạng | Include | Exclude | Hướng xem xét |
|---|---|---|---|
| Ngoài phạm vi định trước | Sai | Có thể sai/đúng | Kiểm tra định nghĩa Include |
| Trúng ngoại lệ | Đúng | Đúng | Kiểm tra định nghĩa Exclude |
| Đủ điều kiện logic | Đúng | Sai | Kiểm tra mô hình join point, weaving và runtime path nếu advice không chạy |
| Loại join point không hỗ trợ | Có thể đúng về mô tả | Có thể sai | Chọn loại join point/cơ chế hỗ trợ phù hợp |

Điều kiện loại trừ thường được đặt với mục đích xử lý **ngoại lệ bên trong miền bao gồm**, chứ không phải làm công cụ thay thế cho việc xác định miền đó.

## 11. Quy tắc loại trừ có phải luôn ưu tiên hơn bao gồm?

Với **một biểu thức pointcut** được định nghĩa đúng là:

```text
P = I AND NOT E
```

thì một điểm vừa thuộc I vừa thuộc E **không được chọn**. Theo logic, E thắng ở **biểu thức này** vì toàn bộ P trả sai.

Tuy nhiên, không nên mở rộng kết luận thành “một exclusion pointcut có thể tắt mọi aspect trong hệ thống”. Giả sử có **hai pointcut độc lập**:

```text
P_A = I AND NOT E
P_B = B
```

Một điểm bị loại khỏi `P_A` vẫn **có thể khớp `P_B`** và kích hoạt advice gắn với `P_B`. Trong một hệ thống có nhiều aspect, mỗi chính sách có miền chọn riêng.

Một số môi trường có thêm cấu hình enable/disable, ordering hoặc các cơ chế điều phối riêng. Chúng không phải là phép phủ định logic mặc nhiên. Vì vậy phải nói rõ **ngoại lệ thuộc pointcut/aspect nào**.

## 12. Exclude rộng quá và exclude hẹp quá

### 12.1. Exclude quá rộng (*over-exclusion*)

Ví dụ:

```text
I = mọi thao tác submit của đơn hàng
E = mọi thao tác được gọi từ phần xử lý nội bộ
```

Nếu gần như mọi thao tác submit đều đi qua một lớp điều phối nội bộ, E có thể loại **gần như toàn bộ Include**, làm chính sách quan sát trở nên vô dụng.

**Cách kiểm soát:** đo tập khớp thực tế, có bảng trường hợp phải chọn và phải loại; chỉ định nghĩa ngoại lệ theo đúng ý nghĩa thay vì dùng một tên lớp/phương thức quá chung.

### 12.2. Exclude quá hẹp (*under-exclusion*)

Ví dụ một chính sách cần bỏ qua cả `submitDraft()` và `submitTestOrder()`, nhưng E chỉ mô tả `submitDraft()`. Khi đó `submitTestOrder()` vẫn được chọn nếu thuộc I.

**Cách kiểm soát:** tổng hợp đầy đủ các nhóm ngoại lệ và kiểm thử từng nhóm. Không phụ thuộc vào việc một ví dụ thử duy nhất đã bị loại.

### 12.3. Include quá rộng và Exclude chắp vá

Có những biểu thức bắt đầu từ “mọi phương thức” rồi loại trừ hàng loạt tên, gói và ngoại lệ. Chúng có thể khó bảo trì khi thêm chức năng mới; một phương thức mới rất dễ lọt vào Include vì chưa có điều kiện Exclude tương ứng.

Thiết kế vững hơn thường bắt đầu từ **vùng bao gồm đủ cụ thể**, sau đó loại các ngoại lệ thực sự. Nếu chỉ dùng một danh sách loại trừ ngày càng dài, cần xem lại liệu điều kiện bao gồm có đang thể hiện đúng chủ đích của chính sách hay không.

## 13. Kiểm thử pointcut phải có ca dương và ca âm

Kiểm thử một pointcut chỉ bằng một điểm “được áp dụng thành công” là chưa đủ. Cần cả:

- **Ca dương (positive):** điểm phải được bao gồm và không bị loại.
- **Ca âm ngoài Include:** điểm vốn không thuộc miền chính sách.
- **Ca âm do Exclude:** điểm thuộc Include nhưng phải bị gỡ.
- **Ca biên:** tên gần giống, overload, giá trị `null`, metadata khác vị trí và điều kiện động.
- **Ca bao phủ kỹ thuật:** điểm đúng logic nhưng bị hạn chế bởi loại join point, phạm vi weaving hoặc đường gọi.

Ví dụ bảng kiểm thử:

| Join point/điều kiện | Kỳ vọng | Lý do |
|---|---|---|
| `orders.submit("VIP")` | Chọn | Thỏa Include, không thỏa Exclude |
| `orders.submit("TEST")` | Không chọn | Thuộc Include nhưng Exclude đúng |
| `orders.cancel("VIP")` | Không chọn | Không thuộc Include |
| Thao tác submit nội bộ | Không chọn | Exclude đúng |
| `reports.submit("VIP")` | Không chọn | Khác phạm vi mô-đun |
| Thao tác có dữ liệu `null` | Phụ thuộc điều kiện đã định nghĩa | Cần quy tắc rõ cho `null` |
| Điểm được chọn nhưng lời gọi không đi qua ranh giới can thiệp | Có thể không kích hoạt advice | Kiểm tra cơ chế và runtime path |

Không được đánh đồng “`P(j)` đúng” với “advice chắc chắn đã chạy”. Một lần thực thi chỉ kích hoạt advice nếu mô hình và cơ chế can thiệp **thực sự quan sát được** điểm đó.

## 14. Các trường hợp biên: overload, metadata, giá trị động

### 14.1. Phương thức overload

```java
void submit(String id);
void submit(String id, boolean dryRun);
```

Đây là **đoạn khai báo minh họa**, không phải chương trình độc lập. Nếu điều kiện Include chỉ xét tên `submit`, nó có thể khớp **cả hai chữ ký**. Nếu muốn loại `dryRun=true`, điều kiện Exclude cần xét ngữ cảnh thích hợp (nếu công cụ hỗ trợ), hoặc hợp đồng thiết kế nên phân biệt rõ mục đích hai phương thức.

Một pointcut chọn đúng chữ ký cần dựa trên loại join point và kiểu đối số, không chỉ dựa vào chữ cái đầu trong tên.

### 14.2. Metadata có thể nằm ở những khai báo khác nhau

Một dấu hiệu dùng làm điều kiện Include/Exclude có thể xuất hiện trên giao diện, lớp triển khai hoặc phương thức cụ thể. Không phải cơ chế nào cũng đọc metadata theo cùng một cách. Nếu điểm “được đánh dấu ngoại lệ” vẫn bị chọn, cần xác định **công cụ đang xét metadata ở đâu** trước khi kết luận biểu thức NOT sai.

### 14.3. Đối số động và `null`

```text
E = tier == "TEST"
```

Điều kiện này không tự định nghĩa cách xử lý `null`, thiếu đối số, hoặc đối tượng con có kiểu khác. Với Java, một cách kiểm tra giá trị chuỗi an toàn là `"TEST".equals(tier)`. Nhưng không nên cho rằng mọi pointcut DSL đều dùng cú pháp Java hoặc có cùng quy tắc so sánh.

### 14.4. Điều kiện về caller, callee và đối tượng đích

Một thao tác có thể được gọi từ nhiều nơi. Nếu Exclude là “bỏ qua lời gọi xuất phát từ caller nội bộ”, cần làm rõ đó là điều kiện tại **method call join point**, **method execution join point có ngữ cảnh luồng điều khiển**, hay một quan sát khác. Cùng tên phương thức không bảo đảm hai mô hình lựa chọn có cùng thông tin caller.

## 15. Khi nào nên dùng điều kiện loại trừ?

Điều kiện loại trừ có ích khi:

1. Chính sách bao gồm có **miền chính ổn định** và chỉ có một số ngoại lệ nhỏ, rõ nghĩa.
2. Ngoại lệ có **lý do kiến trúc hoặc hợp đồng** cụ thể, chẳng hạn tránh quan sát trùng một ranh giới đã được đo riêng.
3. Các điểm bị loại có thể được mô tả bằng điều kiện **ổn định, kiểm thử được**, ít phụ thuộc tên ngẫu nhiên.
4. Mọi ngoại lệ đều được xem xét khi thêm đường gọi hoặc thay đổi chức năng.

Nếu ngoại lệ được dùng để sửa một Include quá chung, làm pointcut khó đọc, hoặc để che một đường thực thi chưa được weaving, cần xem lại thiết kế. Exclude **không chữa** được việc loại join point không được hỗ trợ hoặc cách can thiệp không đi qua điểm mong muốn.

### 15.1. Tên gọi mô tả ý định

Các tên như `orderSubmissionOperations` và `internalDiagnosticOperations` (chỉ là tên khái niệm) thường dễ hiểu hơn những chuỗi wildcard không giải thích ý nghĩa. Một biểu thức có tên nên trả lời được:

- “Chính sách này bao phủ nghiệp vụ/ranh giới gì?”
- “Vì sao nhóm bị loại không cần nhận advice?”
- “Một người thêm phương thức mới sẽ biết quy tắc này áp dụng hay không bằng cách nào?”

## 16. Tương tác giữa nhiều pointcut và nhiều advice

Một join point có thể được nhiều pointcut lựa chọn đồng thời. Ví dụ:

```text
P_metrics = submitOperations AND NOT testOperations
P_audit   = sensitiveOperations
```

Một thao tác `submit` của nhóm nhạy cảm có thể khớp cả hai. Việc nó bị loại khỏi `P_metrics` do thuộc TEST **không nhất thiết làm nó bị loại khỏi `P_audit`**.

Ngoài ra, các advice chạy trên cùng join point có thể ảnh hưởng thứ tự quan sát, giá trị trả về, ngoại lệ hoặc số lần thực thi gốc (đặc biệt với advice bao quanh có khả năng điều phối lời gọi). **Bao gồm/loại trừ là quy tắc lựa chọn, không phải quy tắc tự động xác định thứ tự advice.**

Khi chính sách bao phủ có yêu cầu an toàn hoặc kiểm toán, cần kiểm tra từng aspect và sự phối hợp giữa chúng, không chỉ đếm một log xuất hiện.

## 17. Phân biệt “bị loại trừ” với “không thuộc mô hình join point”

Xét ba trường hợp cùng cho kết quả “không có advice”:

**Trường hợp A — Ngoài Include:** pointcut chọn execution của `submit*`, nhưng thực thi là `cancelOrder()`.

**Trường hợp B — Bị Exclude:** pointcut chọn `submit*` ngoại trừ tier TEST; thực thi là `submitOrder("TEST")`.

**Trường hợp C — Ngoài mô hình/weaving:** pointcut có vẻ chọn mọi `submit*`, nhưng thao tác thực tế là gán trường trực tiếp mà công cụ chỉ chặn được lời gọi phương thức qua proxy; hoặc lời gọi method đi thẳng đến đối tượng đích, không qua proxy.

Cách khắc phục khác nhau:

| Trường hợp | Tầng cần thay đổi nếu muốn có advice |
|---|---|
| Ngoài Include | Điều kiện bao gồm |
| Bị Exclude | Điều kiện loại trừ |
| Loại join point không hỗ trợ | Mô hình/công cụ hoặc ranh giới thiết kế |
| Điểm có hỗ trợ nhưng không được weaving | Phạm vi xử lý mã/cấu hình weaving |
| Lời gọi không đi qua cơ chế can thiệp | Đường thực thi, cách truy cập đối tượng hoặc kỹ thuật weaving |

Một biểu thức `NOT excluded` dù đúng cũng không làm cho một hoạt động ngoài mô hình trở thành join point. Đây là giới hạn **độc lập** với logic tập hợp của Include/Exclude.

## 18. Static matching và dynamic matching

Một số điều kiện có thể dựa trên cấu trúc biết trước, chẳng hạn tên phương thức hoặc lớp khai báo. Những điều kiện khác cần dữ liệu tại thời điểm chạy, chẳng hạn giá trị đối số, trạng thái đối tượng hoặc luồng điều khiển.

Ví dụ:

```text
I_static  = methodName bắt đầu bằng "submit"
E_static  = phương thức thuộc nhóm diagnostic
E_dynamic = tier thực tế bằng "TEST"

P = I_static AND NOT (E_static OR E_dynamic)
```

Khi đánh giá thực tế, một công cụ có thể loại trước những điểm không thỏa điều kiện cấu trúc rồi mới kiểm tra dữ liệu động. Nhưng **thời điểm, mức độ tối ưu và khả năng biểu diễn điều kiện** tùy công cụ.

Điều kiện loại trừ động không được xem là một thuộc tính bất biến của phương thức: cùng `submitOrder(String)`, lời gọi với `"VIP"` và `"TEST"` có thể có kết quả chọn khác nhau.

Cũng phải cẩn thận với môi trường bất đồng bộ: ngữ cảnh theo luồng có thể thay đổi hoặc không được truyền qua tác vụ khác. Nếu Exclude phụ thuộc ngữ cảnh, cần xác định chính xác **nó được đọc tại join point nào**.

## 19. Tối ưu biểu thức mà không thay đổi ngữ nghĩa

Một pointcut nhiều điều kiện có thể được diễn đạt theo các dạng tương đương:

```text
P = I AND NOT (E1 OR E2)
P = I AND NOT E1 AND NOT E2
```

Với predicate thuần, hai cách có cùng kết quả logic. Người đọc có thể chọn cách trực quan hơn. Tuy nhiên:

- Không giả định ngôn ngữ pointcut có cùng ký hiệu/độ ưu tiên với Java.
- Không viết điều kiện chọn có tác dụng phụ để dựa vào thứ tự đánh giá.
- Không mở rộng miền bao gồm chỉ để “tối ưu” nếu làm mất ý nghĩa chính sách.
- Không loại bớt điều kiện Exclude mà chưa chứng minh chúng dư thừa trong **miền Include hiện tại**.

Nếu `E2` chỉ có ý nghĩa ở ngoài Include, nó có thể **không ảnh hưởng ở thời điểm này**; nhưng loại nó khỏi chính sách có thể làm thay đổi hành vi khi Include được mở rộng trong tương lai. Cần dựa trên hợp đồng và kiểm thử, không chỉ trên một tập dữ liệu mẫu.

## 20. Bảo toàn kết quả nghiệp vụ và quan sát đúng

Một pointcut chọn đúng chưa có nghĩa một aspect triển khai đúng. Khi advice tham gia vào luồng xử lý, cần kiểm chứng:

- **Return value** của thao tác gốc có được giữ đúng theo hợp đồng không?
- **Ngoại lệ** được bảo toàn, phân loại hay chuyển đổi có chủ đích?
- **Số lần thực thi** phần nghiệp vụ gốc có đúng không?
- **Kết quả khi Exclude đúng** có hoàn toàn bỏ qua advice mong muốn?
- **Dữ liệu được ghi nhận** có phù hợp và tránh lộ thông tin nhạy cảm?
- **Chi phí** đánh giá điều kiện động và advice có chấp nhận được?

Đặc biệt, không nên đặt một kiểm tra bắt buộc ở pointcut có rủi ro bỏ sót đường đi mà không xác minh vùng bao phủ. Exclude được mô tả để giới hạn chính sách, nhưng một ngoại lệ thiếu chặt chẽ có thể vô tình tạo ra một “lỗ hổng” kiểm soát nếu chính sách liên quan đến tính đúng đắn hoặc an toàn.

## 21. Quy trình xây dựng pointcut có Include và Exclude

1. **Viết một câu mục đích:** ví dụ “Đo thời gian thao tác gửi đơn trong mô-đun orders, ngoại trừ chẩn đoán nội bộ và chế độ TEST”.
2. **Xác định loại join point:** execution hay call, loại method hoặc sự kiện nào? Công cụ có hỗ trợ không?
3. **Định nghĩa Include độc lập:** trước hết chọn chính xác vùng nghiệp vụ cần áp dụng.
4. **Liệt kê Exclude với lý do rõ:** mỗi ngoại lệ nhằm tránh hành vi không mong muốn nào?
5. **Ghép theo logic có dấu ngoặc:** `P = I AND NOT (E1 OR E2)` nếu yêu cầu là bỏ các điểm thuộc bất kỳ ngoại lệ nào.
6. **Liệt kê ca dương và âm:** có điểm khớp toàn bộ, không khớp Include, khớp cả Include/Exclude và các ca biên.
7. **Xác minh mô hình và weaving:** pointcut có thể đúng về logic nhưng không áp dụng ở một đường thực thi thực tế.
8. **Kiểm thử hành vi advice và nghiệp vụ:** bảo toàn kết quả, ngoại lệ, số lần gọi và quan sát đúng điểm.
9. **Rà soát khi đổi API hoặc thêm đường gọi:** một phương thức mới có thể lọt vào Include hoặc Exclude ngoài ý định.

Các bước này giúp pointcut trở thành **một hợp đồng lựa chọn có thể giải thích và kiểm chứng**, không chỉ là một biểu thức wildcard khó đọc.

## 22. Bài tập tự kiểm tra

### Bài 1: Đọc công thức

Cho:

```text
I = methodName STARTS_WITH "process"
E = isInternal OR tier = "TEST"
P = I AND NOT E
```

Điểm nào được chọn?

| Điểm | isInternal | tier | Kết quả |
|---|---|---|---|
| `processOrder` | false | VIP | **Chọn** |
| `processOrder` | false | TEST | Không chọn |
| `processOrder` | true | VIP | Không chọn |
| `cancelOrder` | false | VIP | Không chọn |

**Giải thích:** chỉ hàng đầu thỏa Include và không thỏa Exclude.

### Bài 2: Dấu ngoặc

Một pointcut cần chọn thao tác thuộc A hoặc B nhưng loại tất cả các thao tác nội bộ E. Chọn biểu thức nào?

```text
(1) (A OR B) AND NOT E
(2) A OR (B AND NOT E)
```

**Đáp án:** (1). Với (2), một điểm thuộc A luôn được chọn, kể cả khi E đúng.

### Bài 3: Phủ định quá rộng

Cho `P = NOT isTest`. Vì sao chính sách có thể trở nên quá rộng?

**Đáp án:** đó là phần bù của `isTest` trên toàn miền join point J. Các điểm không phải TEST thuộc nhiều nhóm nghiệp vụ cũng có thể được chọn. Cần một Include xác định miền chính sách.

### Bài 4: Hai aspect độc lập

Điểm `j` vừa khớp `I` vừa khớp `E` trong `P_A = I AND NOT E`. Nhưng `j` đồng thời khớp `P_B` của aspect khác. Advice B có thể chạy không?

**Đáp án:** có thể. Exclude trong `P_A` làm điểm không được chọn **bởi P_A**, không phải cơ chế tắt mọi advice của những pointcut khác.

### Bài 5: Phân tích thiếu log

`submitOrder("VIP")` thỏa Include và không thuộc Exclude, nhưng advice không chạy. Nêu ba khả năng khác.

**Gợi ý:** loại join point cần thiết không nằm trong mô hình công cụ; mã/đối tượng nằm ngoài phạm vi weaving; đường gọi không đi qua cơ chế chặn đang dùng. Cũng cần kiểm tra ca thử có phát sinh join point thật không.

### Bài 6: Thay đổi phạm vi

Trước kia chỉ đo `submitOrder`. Nay phải đo cả `cancelOrder`, nhưng không đo TEST. Phải thay đổi phần nào?

**Đáp án:** mở rộng Include sang `cancelOrder` và giữ Exclude cho nhóm TEST, nếu không có ngoại lệ mới. Sau đó kiểm thử cả hai nhóm.

### Bài 7: Exclude làm chính sách rỗng

Nếu mọi điểm trong Include cũng thuộc Exclude, còn điểm nào được chọn?

**Đáp án:** không có; `Include \ Exclude = ∅`. Đây có thể là cấu hình cố ý, nhưng thường là tín hiệu cần rà soát nếu chính sách được kỳ vọng có độ bao phủ.

## 23. Ghi nhớ

**Include** trả lời “những join point nào nằm trong phạm vi chính sách?”. **Exclude** trả lời “trong phạm vi đó, những join point nào phải bỏ qua?”. Công thức chuẩn để đọc hai nhóm điều kiện là:

```text
Selected = Include AND NOT Exclude
SelectedSet = IncludeSet \ ExcludeSet
```

Khi có nhiều nhóm, dùng **AND/OR/NOT với dấu ngoặc rõ ràng**, kiểm thử cả trường hợp được chọn và bị loại, và bảo đảm ý nghĩa của các điều kiện tĩnh/động phù hợp.

Cuối cùng, phải nhớ rằng một điểm **không được chọn** có thể do **ngoài Include**, **nằm trong Exclude**, **không thuộc mô hình join point**, **không được weaving** hoặc **đường chạy không đi qua cơ chế can thiệp**. Phân biệt đúng nguyên nhân là chìa khóa để thiết kế và chẩn đoán pointcut chính xác.
