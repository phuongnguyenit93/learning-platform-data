# Mã bị phân tán (scattering) và mã bị đan xen (tangling) trong tư duy AOP

> **Mục tiêu học tập:** Nhận diện hai dạng vấn đề thiết kế thường khiến một hệ thống khó bảo trì; giải thích vì sao các mối quan tâm xuyên suốt (*cross-cutting concerns*) tạo ra chúng; thấy cách tư duy lập trình hướng khía cạnh (Aspect-Oriented Programming, AOP) tách phần hành vi dùng chung khỏi nghiệp vụ; và đánh giá được lợi ích, giới hạn, rủi ro khi áp dụng.

## 1. Từ một chức năng nghiệp vụ đến nhiều mối quan tâm

Một phương thức nghiệp vụ thường có trách nhiệm chính, chẳng hạn xác nhận đơn hàng, tính phí hoặc cập nhật tồn kho. Trong ứng dụng thực tế, trước và sau thao tác đó còn có các việc khác:

- **Ghi vết/quan sát:** ghi thời điểm bắt đầu, kết thúc, lỗi và mã tương quan của lời gọi.
- **Đo thời gian:** thu thập thời lượng thực thi cho nhiều nhóm thao tác.
- **Kiểm soát truy cập:** áp dụng chính sách kiểm tra quyền tại những ranh giới xác định.
- **Giao dịch, kiểm toán hoặc áp dụng chính sách lỗi:** thực thi một quy tắc nhất quán tại nhiều vị trí phù hợp.

Những việc này là các **mối quan tâm (concerns)** riêng biệt với quy tắc nghiệp vụ. Khi cùng một mối quan tâm cần xuất hiện tại nhiều điểm của hệ thống, nó có tính chất **xuyên suốt** (*cross-cutting*).

Ví dụ, yêu cầu “ghi nhận mọi thao tác xử lý đơn hàng được quan sát” không thuộc riêng phép tính tiền hay việc xuất kho. Nếu xử lý trực tiếp trong từng phương thức, phần ghi vết có thể lan ra nhiều lớp, còn mỗi phương thức lại chứa cả mã nghiệp vụ lẫn mã ghi vết.

Đó là hai góc nhìn của một vấn đề tổ chức mã:

- **Scattering:** nhìn **theo chiều một mối quan tâm**, mã thực hiện nó nằm rải rác ở nhiều vị trí.
- **Tangling:** nhìn **theo chiều một đơn vị mã**, nhiều mối quan tâm khác nhau bị trộn vào cùng đơn vị đó.

Hai hiện tượng thường xuất hiện cùng nhau, nhưng **không đồng nghĩa** và không bắt buộc cùng tồn tại.

## 2. Scattering: một mối quan tâm bị phân tán ở nhiều nơi

**Scattering** xảy ra khi mã phục vụ một trách nhiệm chung bị phân phối qua nhiều lớp, phương thức hoặc mô-đun. Để thay đổi chính sách chung đó, người bảo trì phải tìm và cập nhật nhiều điểm.

Hình dung có 20 phương thức nghiệp vụ đều tự ghi:

```text
trace("begin", operation);
... nghiệp vụ ...
trace("end", operation);
```

Phần ghi vết nằm ở 20 vị trí. Nếu quy định mới yêu cầu bổ sung mã tương quan hoặc ghi lỗi với cùng định dạng, người phát triển phải sửa nhiều nơi. Có điểm được cập nhật, có điểm bị quên, có điểm dùng định dạng khác: chính sách quan sát trở nên thiếu nhất quán.

**Dấu hiệu nhận biết scattering:**

- Cùng một quy tắc kỹ thuật hoặc đoạn xử lý được lặp lại trong nhiều phương thức.
- Một thay đổi về chính sách yêu cầu sửa hàng loạt tệp không liên quan về nghiệp vụ.
- Khi thêm tính năng nghiệp vụ, lập trình viên phải nhớ chép thêm một “nghi thức” chung.
- Việc đánh giá mức độ bao phủ của chính sách đòi hỏi tìm kiếm thủ công nhiều vị trí.

**Lưu ý:** hai đoạn mã trông giống nhau chưa chắc là scattering cần xử lý bằng AOP. Nếu chúng biểu diễn **hai quy tắc nghiệp vụ khác nhau**, gom lại chỉ vì giống cú pháp có thể gây ràng buộc sai. Cần xác định chúng có thực sự cùng một trách nhiệm và cùng một lý do thay đổi hay không.

## 3. Tangling: nhiều mối quan tâm đan vào cùng một đơn vị mã

**Tangling** xảy ra khi mã của các trách nhiệm khác nhau nằm xen nhau trong một phương thức, lớp hoặc luồng xử lý. Một hàm đặt hàng có thể đồng thời thực hiện:

```text
kiểm tra quyền → ghi trace → kiểm tra dữ liệu → tính tiền
              → đo thời gian → ghi kiểm toán → trả kết quả
```

Ở đây mã nghiệp vụ, quan sát, phân quyền và đo lường bị đan vào một luồng. Kết quả là:

- Khó đọc luồng nghiệp vụ cốt lõi do các thao tác phụ chen giữa.
- Việc thay đổi một chính sách phụ dễ đụng vào mã nghiệp vụ.
- Kiểm thử một hành vi phải thiết lập nhiều phụ thuộc không liên quan.
- Dễ thiếu xử lý trên nhánh ngoại lệ, nhánh trả về sớm hoặc luồng bất đồng bộ.
- Ranh giới trách nhiệm không rõ: lớp nghiệp vụ biết quá nhiều chi tiết quan sát hoặc hạ tầng.

**Tangling không chỉ là “hàm dài”.** Một phương thức ngắn vẫn có thể chứa trách nhiệm không liên quan; ngược lại, một thuật toán nghiệp vụ dài nhưng thống nhất về trách nhiệm chưa chắc bị tangling.

## 4. Cùng một ví dụ Java: vấn đề nhìn từ hai chiều

Đây là chương trình **Java 17+ hoàn chỉnh**, mô phỏng hai nghiệp vụ đơn giản. Mỗi phương thức vừa trả kết quả nghiệp vụ vừa trực tiếp ghi trace.

Lưu tệp `BeforeSeparation.java`:

```java
public class BeforeSeparation {
    static class BillingService {
        String pay() {
            System.out.println("[trace] begin pay");
            String result = "PAID";
            System.out.println("[trace] end pay");
            return result;
        }
    }

    static class ShippingService {
        String ship() {
            System.out.println("[trace] begin ship");
            String result = "SHIPPED";
            System.out.println("[trace] end ship");
            return result;
        }
    }

    public static void main(String[] args) {
        BillingService billing = new BillingService();
        ShippingService shipping = new ShippingService();

        System.out.println(billing.pay());
        System.out.println(shipping.ship());
    }
}
```

Chạy:

```bash
javac BeforeSeparation.java
java BeforeSeparation
```

Kết quả chuẩn:

```text
[trace] begin pay
[trace] end pay
PAID
[trace] begin ship
[trace] end ship
SHIPPED
```

Phân tích theo **scattering**: trách nhiệm “ghi begin/end” được sao chép trong `BillingService` và `ShippingService`. Khi có thêm nghiệp vụ thứ ba, người viết có thể phải sao chép tiếp.

Phân tích theo **tangling**: bên trong từng phương thức, câu lệnh trace chen vào luồng xử lý và phép trả kết quả. Nếu nghiệp vụ có nhiều nhánh trả về hoặc ném ngoại lệ, các câu trace viết thủ công cũng dễ mất cân đối. Ví dụ mã trên **không bảo đảm ghi kết thúc nếu một câu lệnh ở giữa ném ngoại lệ**.

Bởi vậy, cùng một ví dụ cho thấy **một trách nhiệm bị phân tán qua nhiều nơi** và **nhiều trách nhiệm đan trong từng nơi**.

## 5. Bước tách đầu tiên: đưa chính sách dùng chung ra ranh giới

Một cách cải thiện đơn giản là tập trung hành vi ghi vết vào một hàm bao (*wrapper*) và giữ nghiệp vụ chỉ xử lý kết quả của nó. Đây là minh họa **tư duy tách mối quan tâm bằng Java thuần**, chưa phải cơ chế AOP tự động áp dụng vào các điểm thực thi.

Lưu tệp `AfterSeparation.java`:

```java
import java.util.function.Supplier;

public class AfterSeparation {
    static class BillingService {
        String pay() {
            return "PAID";
        }
    }

    static class ShippingService {
        String ship() {
            return "SHIPPED";
        }
    }

    static <T> T trace(String operation, Supplier<T> action) {
        System.out.println("[trace] begin " + operation);
        try {
            return action.get();
        } finally {
            System.out.println("[trace] end " + operation);
        }
    }

    public static void main(String[] args) {
        BillingService billing = new BillingService();
        ShippingService shipping = new ShippingService();

        System.out.println(trace("pay", billing::pay));
        System.out.println(trace("ship", shipping::ship));
    }
}
```

Chạy:

```bash
javac AfterSeparation.java
java AfterSeparation
```

Kết quả chuẩn:

```text
[trace] begin pay
[trace] end pay
PAID
[trace] begin ship
[trace] end ship
SHIPPED
```

Đối chiếu:

| Tiêu chí | Trước khi tách | Sau khi tách qua wrapper |
|---|---|---|
| Vị trí xử lý trace | Nằm trong từng phương thức nghiệp vụ | Nằm trong hàm `trace` |
| Độ tập trung của chính sách | Lặp ở nhiều nơi | Một nơi định nghĩa |
| Khả năng đọc nghiệp vụ | Trace chen vào mã nghiệp vụ | Phương thức nghiệp vụ tập trung vào kết quả |
| Điểm áp dụng chính sách | Trong phương thức, dễ bỏ sót | Tại từng lời gọi wrapper, **vẫn phải nhớ dùng** |
| Nhánh ngoại lệ | Có thể thiếu log kết thúc | `finally` chạy khi `action.get()` kết thúc bình thường hoặc bằng ngoại lệ |

**Hai giới hạn cần hiểu rõ:**

1. Dù thân phương thức nghiệp vụ sạch hơn, nơi gọi vẫn phải chủ động viết `trace(...)`. Người gọi bỏ quên wrapper thì chính sách không được áp dụng. Mức độ scattering ở **điểm áp dụng** vì vậy chưa chắc được giải quyết triệt để.
2. Dòng `[trace] end` ở `finally` chỉ có nghĩa là **đã rời phạm vi thực thi**, không chứng minh lời gọi thành công. Nếu cần tách thành công/thất bại thì chính sách trace phải phân biệt kết quả bình thường với ngoại lệ. `Supplier<T>` cũng chỉ phù hợp trực tiếp cho tác vụ không khai báo checked exception; ví dụ không phải một cơ chế bao phủ mọi loại lời gọi.

Điểm học quan trọng: **tách chỗ định nghĩa một chính sách** và **tập trung cách chọn những nơi áp dụng chính sách** là hai việc khác nhau. Tư duy AOP đưa việc chọn điểm áp dụng thành một cấu phần thiết kế rõ ràng.

## 6. AOP xử lý scattering và tangling theo cơ chế nào?

**Aspect-Oriented Programming (AOP)** mô-đun hóa những mối quan tâm cắt ngang nhiều phần của chương trình. Thay vì chèn thủ công cùng một đoạn kỹ thuật vào từng đơn vị nghiệp vụ, ta mô tả **điểm nào cần áp dụng** và **hành vi nào cần thực hiện** ở các điểm đó.

Các thuật ngữ nền tảng:

| Thuật ngữ | Ý nghĩa trong tư duy AOP | Liên hệ với ví dụ |
|---|---|---|
| **Concern** | Một trách nhiệm hoặc mục đích xử lý có thể xác định | Ghi trace, tính tiền |
| **Cross-cutting concern** | Concern cần xuất hiện tại nhiều ranh giới hoặc điểm xử lý | Trace ở nhiều nghiệp vụ |
| **Join point** | Một điểm trong quá trình chạy/cấu trúc chương trình mà một mô hình AOP có thể tác động | Thực thi phương thức `pay()` |
| **Pointcut** | Quy tắc chọn một tập join point | Chọn thực thi `pay()` và `ship()` |
| **Advice** | Hành vi được thực hiện tại các join point được chọn | Ghi begin/end quanh lời gọi |
| **Aspect** | Mô-đun kết hợp chính sách/pointcut/advice liên quan | Khía cạnh quan sát lời gọi |
| **Weaving** | Quá trình kết hợp hành vi của aspect với mã/chương trình đích | Nối trace vào các điểm đã chọn |

**Mô hình khái niệm:**

```text
   Mã nghiệp vụ                 Mô-đun aspect
  ┌────────────────┐          ┌─────────────────────────┐
  │ pay()          │          │ Pointcut: chọn pay/ship  │
  │ ship()         │          │ Advice: trace begin/end  │
  └────────────────┘          └─────────────────────────┘
            \                         /
             \_____ weaving ________/
                       |
                       v
           Lời gọi thực thi có trace
           mà không cần chèn trace
           vào thân từng phương thức
```

Pseudocode dưới đây chỉ diễn đạt **ý tưởng**, không phải cú pháp của một ngôn ngữ AOP cụ thể:

```text
aspect Tracing:
    pointcut observed = execution(pay) OR execution(ship)

    around observed:
        log("begin", currentOperation)
        try:
            return proceed()  // tiếp tục phần xử lý gốc
        finally:
            log("end", currentOperation)
```

Khi quy tắc chọn điểm thực thi và hành vi trace được mô-đun hóa tập trung:

- **Giảm scattering:** định nghĩa trace và quy tắc chọn các nghiệp vụ áp dụng nằm trong một mô-đun chính sách, không sao chép trong từng phương thức.
- **Giảm tangling:** thân `pay()`, `ship()` không phải chứa những câu lệnh quan sát không thuộc logic nghiệp vụ.
- **Tăng khả năng thay đổi đồng bộ:** đổi định dạng hoặc chính sách trace tại đúng nơi sở hữu nó.

Tuy nhiên, **aspect không làm chi phí phối hợp biến mất**. Hành vi thực thi còn phụ thuộc cấu hình pointcut, loại join point mà cơ chế AOP hỗ trợ, thời điểm weaving và thứ tự áp dụng advice. Mã nghiệp vụ có thể sạch hơn trong khi đường đi thực thi trở nên khó nhìn bằng cách chỉ mở một tệp nguồn.

### 6.1. Before, after và around khác nhau ra sao?

- **Before:** hành vi chạy trước join point đã chọn; hữu ích cho ghi nhận đầu vào hoặc kiểm tra điều kiện trước khi tiến hành.
- **After:** hành vi chạy khi thoát join point; một số mô hình phân biệt hoàn tất bình thường, thoát do ngoại lệ và trường hợp cuối cùng bất kể kết quả.
- **Around:** bao quanh lời gọi, thường điều khiển việc tiếp tục thực thi gốc qua một cơ chế tương tự `proceed()`; linh hoạt nhưng có ảnh hưởng lớn nhất đến luồng điều khiển.

Không được suy từ cái tên “after” rằng nó luôn có cùng nghĩa trong mọi công cụ. Khi cần log đúng “thành công”, “thất bại”, “rời phạm vi”, hãy định nghĩa riêng từng trạng thái và kiểm chứng trên công cụ triển khai thực tế.

### 6.2. Weaving diễn ra lúc nào?

Tùy công cụ và mô hình thực thi, việc kết hợp aspect có thể được thực hiện khi biên dịch, khi xử lý mã đã biên dịch, khi tải lớp hoặc tại thời điểm chạy bằng cơ chế trung gian. Những cách này có **phạm vi join point, giới hạn kỹ thuật và chi phí** khác nhau. Vì thế AOP là **cách tổ chức mối quan tâm**, không đồng nhất với một kỹ thuật chặn lời gọi duy nhất.

## 7. Phân biệt scattering và tangling trong ca thực tế

| Quan sát | Nhấn mạnh scattering | Nhấn mạnh tangling |
|---|---|---|
| “Mỗi lớp lại có một đoạn ghi kiểm toán giống nhau.” | Có: một chính sách nằm nhiều nơi | Có thể có nếu đoạn kiểm toán chen vào nghiệp vụ |
| “Một phương thức dài chứa kiểm tra quyền, tính giá, gửi thông báo và ghi số liệu.” | Chưa thể kết luận chỉ từ một phương thức | Có dấu hiệu: nhiều trách nhiệm bị ghép vào một nơi |
| “Đổi format log phải sửa 12 lớp.” | Rất rõ | Có thể là hệ quả kèm theo |
| “Muốn hiểu tính giá phải lần qua nhiều nhánh kiểm soát kỹ thuật.” | Chưa đủ bằng chứng | Rất rõ |
| “Một số thao tác có audit, một số thao tác quên audit.” | Có dấu hiệu phân tán việc áp dụng | Không bắt buộc |

Có thể xem cấu trúc hệ thống như một ma trận:

```text
                       Đơn vị mã
Mối quan tâm       Billing    Shipping    Inventory
----------------------------------------------------
Nghiệp vụ             X           X            X
Tracing               X           X            X
Kiểm toán             X                        X
Đo thời gian          X           X
```

Đọc **theo hàng**: concern Tracing xuất hiện qua nhiều đơn vị mã → nguy cơ **scattering**. Đọc **theo cột**: Billing chứa nghiệp vụ, Tracing, kiểm toán, đo thời gian → nguy cơ **tangling**.

Ma trận chỉ là cách soi cấu trúc, không phải tiêu chí máy móc “cứ có hai dấu X là mã xấu”. Một số ranh giới kỹ thuật hoặc nghiệp vụ **cần phối hợp rõ ràng** và việc gom quá mức có thể làm mất ngữ nghĩa.

## 8. Vì sao hai hiện tượng làm tăng chi phí thay đổi?

### 8.1. Tăng số điểm phải chỉnh sửa

Khi một chính sách chung rải ở nhiều nơi, phạm vi thay đổi lớn hơn phạm vi lý do thay đổi. Sửa một yêu cầu trace nhưng phải rà soát toàn bộ các nhóm nghiệp vụ làm tăng nguy cơ thiếu sót và sai lệch giữa các bản sao.

### 8.2. Làm luồng nghiệp vụ khó kiểm chứng

Nếu điều kiện nghiệp vụ bị bao quanh bởi nhiều câu lệnh kỹ thuật, người đọc khó xác định đoạn nào làm thay đổi trạng thái nghiệp vụ. Kiểm thử cũng có thể bị buộc khởi tạo thêm logger, bộ đo, kiểm soát quyền và trạng thái hạ tầng.

### 8.3. Khiến đường lỗi thiếu nhất quán

Một phương thức có thể trả sớm hoặc ném ngoại lệ. Mã trace viết nối tiếp ở cuối hàm chỉ chạy nếu chương trình đi tới dòng đó. Việc lặp cấu trúc này ở nhiều phương thức khiến lỗi cùng loại cũng phân tán.

### 8.4. Làm chính sách xuyên suốt khó kiểm toán

Một quy tắc kiểm toán hoặc quan sát được xem là đáng tin chỉ khi biết rõ **điểm nào được bao phủ, điểm nào loại trừ và điều gì xảy ra khi chính sách thất bại**. Càng nhiều vị trí chép thủ công, phạm vi bao phủ càng khó chứng minh.

## 9. Khi nào AOP là lựa chọn phù hợp?

AOP đáng cân nhắc khi một hành vi có **chính sách chung, ranh giới áp dụng có thể mô tả ổn định và ít phụ thuộc vào chi tiết nghiệp vụ bên trong**. Ví dụ ghi trace nhất quán tại các thao tác công khai của một nhóm dịch vụ là ứng viên dễ hiểu.

Trái lại, logic “khách hàng hạng đặc biệt được giảm 7% khi mua loại hàng A” là **quy tắc nghiệp vụ**, thường nên được mô hình hóa thành hành vi hoặc chính sách nghiệp vụ có tên rõ ràng. Che giấu quy tắc cốt lõi trong một advice chung có thể khiến kết quả tính toán bất ngờ.

| Cách tiếp cận | Điểm mạnh | Điểm cần chú ý |
|---|---|---|
| **Hàm dùng chung** | Tập trung định nghĩa, đơn giản, dễ theo dấu | Từng nơi vẫn phải gọi |
| **Decorator/wrapper** | Ranh giới rõ, dễ chủ động ghép và kiểm thử | Phải bảo đảm mọi đường gọi cần thiết đi qua lớp bao |
| **Interceptor/middleware** | Phù hợp với một pipeline hoặc giao thức cụ thể | Chỉ bao phủ các điểm mà pipeline quản lý |
| **AOP với pointcut/advice** | Tập trung cả hành vi và quy tắc chọn điểm áp dụng | Có thể tạo phụ thuộc ngầm, khó lần dấu và phụ thuộc giới hạn weaving |

Các lựa chọn này không loại trừ lẫn nhau. Tư duy AOP giúp **nhận diện trách nhiệm xuyên suốt**; quyết định triển khai nên dựa trên nơi phát sinh hành vi, khả năng quan sát, nhu cầu kiểm thử và độ phức tạp thực tế.

## 10. Góc nhìn nâng cao: rủi ro khi “tách sạch” mã nghiệp vụ

### 10.1. Pointcut quá rộng hoặc quá hẹp

Ví dụ một pointcut chọn mọi phương thức có tên bắt đầu bằng `save` có thể vô tình áp dụng vào thao tác không thuộc chính sách quan sát dự kiến (**quá rộng**) và bỏ qua thao tác cùng ý nghĩa nhưng mang tên khác (**quá hẹp**).

Nên ưu tiên ranh giới có ngữ nghĩa ổn định và ghi rõ tập thao tác được bao phủ. Sau khi đổi tên, tách lớp hoặc bổ sung phương thức mới, cần đánh giá lại pointcut.

### 10.2. Hành vi ngầm và thứ tự aspect

Khi nhiều aspect cùng áp dụng tại một join point, thứ tự của chúng có thể ảnh hưởng đến kết quả. Ví dụ kiểm soát truy cập nên xảy ra ở đâu so với đo thời gian hoặc ghi kiểm toán? Nếu đo thời gian nằm bên ngoài một lớp bao khác, số đo bao gồm chi phí của lớp đó; nếu nằm bên trong thì không.

Hãy định nghĩa rõ thứ tự có ý nghĩa và viết kiểm thử ở **ranh giới quan sát được**, thay vì giả định mọi thứ đều hoán đổi được.

### 10.3. Lời gọi nội bộ và phạm vi có thể chặn

Không phải mọi mô hình weaving đều nhìn thấy cùng một loại join point. Với kỹ thuật trung gian ở ranh giới đối tượng, một lời gọi **tự thực hiện bên trong đối tượng** có thể không đi qua lớp trung gian; cơ chế weaving ở mức mã có thể có phạm vi khác. Vì vậy, “đã cấu hình pointcut” **không tự chứng minh** rằng mọi lối đi đều được bao phủ.

Khi thiết kế, cần chỉ rõ đối tượng mục tiêu, cách lời gọi đi vào, loại join point được hỗ trợ và các trường hợp bỏ qua.

### 10.4. Thay đổi ngữ nghĩa do advice quanh lời gọi

Advice dạng around có thể bỏ qua, thay đổi tham số, đổi ngoại lệ, biến đổi giá trị trả về hoặc gọi phần xử lý gốc nhiều lần, tùy cơ chế. Đây là sức mạnh và cũng là nguy cơ. Một advice tự động thử lại thao tác thanh toán có tác dụng phụ, chẳng hạn, cần quy tắc chống thực hiện trùng và hợp đồng lỗi rõ ràng.

Điều kiện quan trọng của một aspect quan sát thuần túy là **không vô ý làm thay đổi kết quả nghiệp vụ**: giá trị trả về, ngoại lệ và số lần thực thi gốc phải được giữ nguyên theo hợp đồng đã chọn.

### 10.5. Tác vụ bất đồng bộ và phạm vi ngữ cảnh

Một lời gọi kết thúc có thể chỉ trả về đối tượng đại diện cho tác vụ chưa hoàn thành. Advice chạy quanh **lời gọi tạo tác vụ** không đương nhiên đo đến lúc tác vụ hoàn tất. Tương tự, thông tin tương quan theo luồng thực thi có thể không tự chuyển sang luồng khác.

Cần quyết định đang đo **thời gian gọi**, **thời gian hoàn tất công việc** hay **thời gian trọn một yêu cầu**. Những phạm vi này khác nhau; đặt advice sai điểm khiến số liệu đúng kỹ thuật nhưng sai ý nghĩa.

### 10.6. Chi phí, bảo mật dữ liệu và khả năng chẩn đoán

Một chính sách quan sát có thể tạo thêm chi phí I/O, cấp phát, ghi log hoặc thu thập dữ liệu nhạy cảm. Tách thành aspect không loại bỏ các chi phí đó. Chỉ ghi dữ liệu cần thiết, hạn chế thông tin bí mật, có khả năng bật/tắt hoặc điều chỉnh mức chi tiết hợp lý và đo đạc trước khi đưa ra kết luận về hiệu năng.

Ngoài kiểm thử nghiệp vụ, cần có cách xác định **aspect nào đã áp dụng vào join point nào** để điều tra khi đường thực thi không khớp với mã nguồn nhìn thấy.

## 11. Quy trình cải thiện thiết kế mà không che giấu nghiệp vụ

1. **Liệt kê mối quan tâm:** phân biệt quy tắc nghiệp vụ (tính tiền, xuất kho) với quy tắc xuyên suốt (trace, kiểm toán, đo thời gian).
2. **Lập bản đồ xuất hiện:** tìm các điểm lặp cùng chính sách (**scattering**) và các phương thức chứa nhiều trách nhiệm (**tangling**). Xác định nơi bắt đầu/kết thúc mỗi thao tác.
3. **Chọn một chính sách có hợp đồng rõ:** ví dụ trace phải ghi tên thao tác, thời điểm bắt đầu, cách kết thúc, và không đổi giá trị/ngoại lệ nghiệp vụ.
4. **Tách phần định nghĩa hành vi:** đưa chính sách khỏi thân nghiệp vụ, trước tiên bằng hàm hay wrapper nếu phù hợp; cân nhắc pointcut/advice khi quy tắc áp dụng thực sự xuyên suốt.
5. **Xác định phạm vi bao phủ:** nêu rõ thao tác được áp dụng, loại trừ, lời gọi nội bộ, trường hợp đồng bộ/bất đồng bộ và đường ngoại lệ.
6. **Kiểm thử trước–sau:** bảo toàn kết quả nghiệp vụ, kiểm tra cả lỗi và tác dụng phụ, xác minh chính sách xuất hiện đúng một lần tại các điểm dự định.
7. **Đánh giá độ rõ ràng sau tách:** người đọc có xác định được lý do một aspect chạy hay không? Nếu quá khó quan sát, cần ranh giới hoặc tên gọi rõ hơn.

**Không nên chuyển mọi dòng dùng chung sang aspect.** Mục tiêu là giảm số lý do thay đổi trong một đơn vị mã và giảm số nơi phải chỉnh sửa cho một chính sách, trong khi giữ được khả năng giải thích luồng chạy.

## 12. Bài tập tự kiểm tra

Xét ba tình huống:

**A.** Mười phương thức tự chèn đoạn “bắt đầu → xử lý → kết thúc”; một phương thức quên ghi khi trả về sớm.

**B.** Chỉ có một phương thức xuất hóa đơn, nhưng trong đó trộn tính thuế, in thông báo chẩn đoán, kiểm tra chính sách truy cập và cập nhật số liệu quan sát.

**C.** Quy tắc khuyến mãi cho đơn hàng bị nhân bản tại hai màn hình, nhưng hai màn hình có điều kiện bán hàng khác nhau.

**Gợi ý trả lời:**

- **A:** dấu hiệu rõ của **scattering** vì một chính sách quan sát phải lặp trên nhiều điểm; có thể kèm **tangling** trong từng phương thức. Cần định nghĩa rõ hành vi tại nhánh trả về sớm và ngoại lệ.
- **B:** dấu hiệu rõ của **tangling** vì nhiều trách nhiệm bị đặt trong cùng luồng; từ một phương thức đơn lẻ **chưa đủ kết luận scattering**.
- **C:** trước khi gom, phải làm rõ hai bản sao cùng một chính sách hay khác nhau về quy tắc nghiệp vụ. Không tự động chọn AOP chỉ vì thấy mã trùng.

Có thể kiểm tra thiết kế bằng bốn câu hỏi: **(1)** Một chính sách chung có đang được chép nhiều nơi không? **(2)** Một phương thức có chứa nhiều lý do độc lập để thay đổi không? **(3)** Sau khi tách, điều gì quyết định điểm áp dụng? **(4)** Giá trị trả về, ngoại lệ và số lần thực thi nghiệp vụ có còn đúng hợp đồng không?

## 13. Ghi nhớ

**Scattering** là *một mối quan tâm trải ra nhiều đơn vị mã*; **tangling** là *nhiều mối quan tâm đan vào một đơn vị mã*. Chúng là hai chiều độc lập để đánh giá cấu trúc chương trình. AOP đưa ra cách mô-đun hóa mối quan tâm xuyên suốt bằng **aspect**, mô tả **join point/pointcut**, gắn **advice** thông qua **weaving**. Một thiết kế tốt vừa giảm việc lặp chính sách, vừa làm nghiệp vụ dễ hiểu, đồng thời luôn kiểm chứng ranh giới áp dụng, đường lỗi, thứ tự và hành vi thực thi thực tế.
