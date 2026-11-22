# Phân biệt yêu cầu bắt buộc, quy ước và chi tiết triển khai trong Java Object Contract

## 1. Đọc một quy tắc Java đúng cấp độ

Khi nói một đối tượng Java có “contract” (hợp đồng hành vi), ta cần phân biệt ba cấp độ:

1. **Yêu cầu bắt buộc (contract/API specification):** Điều kiện mà phương thức hoặc kiểu dữ liệu đã công bố phải tuân thủ để mã khác có thể dựa vào. Vi phạm dẫn đến hành vi sai về mặt ngữ nghĩa dù chương trình vẫn biên dịch.
2. **Quy ước hoặc khuyến nghị (convention/best practice):** Cách viết giúp API dễ hiểu, dễ bảo trì, ít lỗi hoặc hiệu quả hơn. Có trường hợp vi phạm quy ước không làm sai hợp đồng của Java.
3. **Chi tiết triển khai (implementation detail):** Lựa chọn bên trong một class, thư viện hoặc phiên bản JDK. Nó có thể quan sát được ở một môi trường cụ thể nhưng không phải bảo đảm chung để mã ứng dụng phụ thuộc vào.

Trong chủ đề `object-contract`, điểm xuất phát là `java.lang.Object`: mọi class đều kế thừa các phương thức như `equals(Object)`, `hashCode()` và `toString()`. Ba phương thức này có mức ràng buộc khác nhau. Học thuộc một ví dụ triển khai mà không phân biệt cấp độ rất dễ dẫn đến suy luận sai, đặc biệt khi đối tượng được đưa vào `HashMap`, `HashSet` hoặc thư viện bên thứ ba.

Một câu hỏi tự kiểm tra hữu ích là: **“Nếu tôi thay phần hiện thực nhưng giữ nguyên hành vi đã được tài liệu cam kết, chương trình của bên gọi có còn đúng không?”** Nếu có, phần bị thay thường là chi tiết triển khai.

## 2. Các yêu cầu bắt buộc của `equals(Object)`

Khi một class định nghĩa khái niệm “hai giá trị bằng nhau” qua `equals`, quan hệ đó phải có các tính chất sau:

| Tính chất | Yêu cầu | Ví dụ |
| --- | --- | --- |
| Phản xạ (*reflexive*) | Với đối tượng khác `null`, `x.equals(x)` là `true`. | Một `UserId("u1")` bằng chính nó. |
| Đối xứng (*symmetric*) | Với `x` và `y` khác `null`, `x.equals(y)` và `y.equals(x)` phải cho cùng kết quả. | Nếu ID A bằng ID B, chiều ngược lại cũng bằng. |
| Bắc cầu (*transitive*) | Nếu `x.equals(y)` và `y.equals(z)` thì `x.equals(z)`. | Ba đối tượng mô tả cùng ID phải nhất quán. |
| Nhất quán (*consistent*) | Gọi lặp lại cho cùng kết quả khi thông tin dùng để so sánh chưa thay đổi. | Không đổi trường ID thì kết quả không tự đổi. |
| So với `null` | Với `x` khác `null`, `x.equals(null)` là `false`. | Không có đối tượng hợp lệ nào bằng `null`. |

Đây là **hợp đồng hành vi**, không phải gợi ý về cách viết. `Object.equals` mặc định dùng đồng nhất tham chiếu: hai tham chiếu trỏ cùng đối tượng thì bằng nhau. Class có thể override để dùng *value equality* (bằng nhau theo giá trị), miễn là vẫn giữ đủ các tính chất trên.

Phân biệt hai phép so sánh:

- `a == b` kiểm tra hai biến tham chiếu có trỏ cùng đối tượng hay không.
- `a.equals(b)` gọi cách định nghĩa “bằng nhau” của class; có thể giống `==` hoặc so sánh dữ liệu.

**Lưu ý về kế thừa:** Dùng `instanceof` hay `getClass()` trong `equals` là một **quyết định thiết kế**, không có quy tắc chung bắt mọi class chọn một cách. Nếu class mở cho kế thừa, phải xét cả quan hệ đối xứng và bắc cầu giữa đối tượng cha/con. Một class `final` với các trường giá trị bất biến thường giúp định nghĩa equality dễ an toàn hơn.

## 3. Hợp đồng `hashCode()` gắn chặt với `equals()`

`hashCode` có ba điểm quan trọng trong tài liệu Java:

1. Trong cùng một lần chạy ứng dụng, việc gọi `hashCode()` nhiều lần trên một đối tượng phải trả về cùng một số nguyên **nếu thông tin dùng trong `equals` của đối tượng ấy không bị thay đổi**. Không có cam kết mã băm giữ nguyên qua hai lần chạy chương trình khác nhau.
2. **Nếu `a.equals(b) == true` thì bắt buộc `a.hashCode() == b.hashCode()`.** Vì thế, khi override `equals` để định nghĩa equality theo giá trị, thông thường phải override `hashCode` cho phù hợp.
3. Nếu `a.equals(b) == false` thì **không bắt buộc** hai mã băm phải khác nhau. Va chạm hash (*collision*) là hợp lệ.

Dạng logic cần nhớ:

`a.equals(b) ⇒ a.hashCode() == b.hashCode()`

Chiều ngược lại **không đúng nói chung**: cùng mã băm không có nghĩa là hai đối tượng bằng nhau.

Tại sao cần quy tắc này? Cấu trúc dữ liệu dựa trên hash như `HashSet` và `HashMap` sử dụng mã băm để tổ chức việc tìm phần tử rồi dùng so sánh equality để phân biệt khóa phù hợp. Nếu hai khóa bằng nhau nhưng cho mã băm khác nhau, các thao tác thêm/tìm kiếm/xóa có thể cho kết quả sai so với kỳ vọng về khóa bằng nhau.

Việc dùng một thuật toán hash “đẹp” hoặc một công thức `31 * result + fieldHash` là **quy ước triển khai**, không phải yêu cầu bắt buộc của contract. Ngay cả `hashCode() { return 1; }` cũng thỏa điều kiện “bằng nhau thì cùng hash” cho mọi cặp đối tượng, nhưng thường làm suy giảm hiệu năng đáng kể vì va chạm quá nhiều.

## 4. Ví dụ Java 17 chạy được: giữ đúng contract

Ví dụ sau coi hai `UserId` bằng nhau khi có cùng chuỗi mã, bất kể chúng là hai đối tượng được tạo riêng.

```java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class ObjectContractDemo {
    static final class UserId {
        private final String value;

        UserId(String value) {
            this.value = Objects.requireNonNull(value);
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof UserId that)) {
                return false;
            }
            return value.equals(that.value);
        }

        @Override
        public int hashCode() {
            return value.hashCode();
        }

        @Override
        public String toString() {
            return "UserId[" + value + "]";
        }
    }

    public static void main(String[] args) {
        UserId a = new UserId("U-42");
        UserId b = new UserId("U-42");
        Set<UserId> ids = new HashSet<>();
        ids.add(a);

        System.out.println(a == b);
        System.out.println(a.equals(b));
        System.out.println(a.hashCode() == b.hashCode());
        System.out.println(ids.contains(b));
        System.out.println(a);
    }
}
```

Lưu tệp `ObjectContractDemo.java`, sau đó chạy:

```bash
javac ObjectContractDemo.java
java ObjectContractDemo
```

Kết quả chuẩn:

```text
false
true
true
true
UserId[U-42]
```

Giải thích từng dòng:

1. `false`: `a` và `b` được tạo bằng hai lần `new`, nên là hai đối tượng khác nhau.
2. `true`: phương thức `equals` so sánh `value`, không so sánh địa chỉ tham chiếu.
3. `true`: hai `value` bằng nhau nên cùng mã băm.
4. `true`: `HashSet` nhận ra khóa cùng giá trị nhờ cặp `hashCode`/`equals` nhất quán.
5. `UserId[U-42]`: đây là định dạng do class **tự chọn** cho `toString`, không phải mẫu đầu ra Java bắt buộc cho mọi đối tượng.

Class này là `final`, trường `value` là `final` và không có setter nên giá trị dùng trong equality ổn định sau khi khởi tạo. Điều đó thuận lợi khi dùng `UserId` làm khóa của cấu trúc dữ liệu dựa trên hash.

## 5. Cùng một vấn đề nhưng ba cấp độ khác nhau

| Phát biểu | Phân loại | Lý do |
| --- | --- | --- |
| “`equals` phải phản xạ, đối xứng, bắc cầu, nhất quán và trả về `false` khi so với `null`.” | **Bắt buộc** | Là contract đã công bố của `Object.equals`. |
| “Hai đối tượng bằng nhau theo `equals` phải cùng `hashCode`.” | **Bắt buộc** | Là ràng buộc giữa hai phương thức. |
| “Hai đối tượng khác nhau phải có hai mã băm khác nhau.” | **Sai** | Java cho phép hash collision. |
| “Mỗi class đều phải override `equals`, `hashCode` và `toString`.” | **Sai** | Có thể giữ hành vi mặc định của `Object` nếu phù hợp bài toán. |
| “Một class có value equality nên tránh biến đổi các trường dùng để tính equality khi đang làm hash key.” | **Khuyến nghị rất quan trọng** | Giữ hoạt động tra cứu đáng tin cậy; đột biến khóa gây lỗi sử dụng collection. |
| “Dùng `Objects.equals`, `Objects.hash` để viết mã rõ ràng.” | **Quy ước/lựa chọn** | Là tiện ích, không phải cách viết duy nhất đúng contract. |
| “Lấy số 31 để phối hợp các trường khi tính hash.” | **Lựa chọn triển khai** | Phổ biến nhưng không được contract bắt buộc. |
| “Thứ tự duyệt một `HashMap` luôn là thứ tự thêm vào.” | **Sai** | Không có bảo đảm thứ tự duyệt như `LinkedHashMap`. |
| “Giá trị `hashCode` phải giống nhau giữa các lần khởi động JVM.” | **Sai** | Hợp đồng không cam kết ổn định qua các lần chạy. |
| “`toString` nên dễ đọc, hữu ích khi log/debug và không tiết lộ thông tin nhạy cảm.” | **Quy ước thiết kế** | Định dạng cụ thể do class/API quyết định. |
| “Máy ảo bắt buộc tạo identity hash từ địa chỉ RAM của đối tượng.” | **Sai** | Cách sinh identity hash là chi tiết thực thi, không phải cam kết như vậy của Java. |

Điểm mấu chốt: một câu có vẻ “rất thường gặp trong mã Java” chưa chắc là một ràng buộc chính thức. Muốn đánh giá đúng, phải đọc lời cam kết của API, sau đó phân biệt với hướng dẫn thiết kế và thuật toán cụ thể.

## 6. `toString()`: mục đích mô tả và định dạng cụ thể

Tài liệu `Object.toString()` mô tả mục đích là cung cấp biểu diễn ngắn gọn, có ích cho người đọc, và khuyến khích class override để cung cấp thông tin phù hợp. `Object.toString` mặc định tạo chuỗi dạng tên class, dấu `@` và mã băm ở hệ thập lục phân. Tuy nhiên, **không có hợp đồng phổ quát** buộc mọi class override `toString` phải giữ dạng ấy hoặc phải xuất mọi trường theo một định dạng chung.

Ví dụ, cả hai kiểu dưới đây đều có thể là lựa chọn triển khai hợp lý, tùy API:

`UserId[U-42]`

`UserId(value=U-42)`

Bài học thực tiễn:

- Dùng `toString` để chẩn đoán và đọc log, nhưng không coi biểu diễn mặc định là định dạng trao đổi dữ liệu ổn định.
- Không parse đầu ra `toString` của thư viện bên thứ ba để làm quy tắc nghiệp vụ, trừ khi chính thư viện **công bố rõ** định dạng đó là một phần API.
- Tránh đưa mật khẩu, token, khóa bí mật hoặc dữ liệu cá nhân nhạy cảm vào `toString` vì log có thể lưu trữ lâu dài.
- Nếu hệ thống cần biểu diễn máy đọc được, dùng hợp đồng serialization được định nghĩa riêng, chẳng hạn schema JSON rõ ràng.

Một class có thể ghi thành công dữ liệu nghiệp vụ dù không override `toString`. Bởi vậy “phải luôn override `toString`” là kết luận quá mức.

## 7. Trường hợp lỗi: vi phạm contract và vi phạm quy ước

### 7.1. Vi phạm thực sự: equality theo giá trị, hash theo identity

Giả sử class định nghĩa `equals` dựa vào `id`, nhưng lại viết:

```java
@Override
public int hashCode() {
    return System.identityHashCode(this);
}
```

Đây là **đoạn mã minh họa cần đặt trong class**, không phải chương trình độc lập. `System.identityHashCode` cho mã băm theo nhận diện của đối tượng mà không sử dụng cách equality đã override. Hai thể hiện khác nhau có thể có cùng `id` (và vì vậy `equals` trả `true`) nhưng có identity hash khác nhau. Thiết kế này **không bảo đảm** yêu cầu “equals bằng thì hash bằng”. Không thể viện lý do “code chạy được” để coi nó đúng contract.

Cách sửa là tính hash từ cùng các trường xác định equality, chẳng hạn `return id.hashCode();` nếu `id` không phải `null`. Cũng cần đảm bảo mọi trường dùng trong `equals` được tính một cách nhất quán khi xác định `hashCode`; không nhất thiết dùng mọi trường trong hash, nhưng phải giữ điều kiện hai giá trị bằng nhau có hash bằng nhau.

### 7.2. Không vi phạm contract: nhiều giá trị chung một hash

```java
@Override
public int hashCode() {
    return 1;
}
```

Đây cũng chỉ là phương thức minh họa đặt trong class. Nếu `equals` đúng và mọi đối tượng đều trả mã băm `1`, quy tắc tương thích vẫn đúng. Vấn đề ở đây là **hiệu năng**, không phải tính hợp lệ của equality contract. Muốn cải thiện phân bố hash có thể chọn thuật toán khác, miễn giữ ràng buộc bắt buộc.

### 7.3. Lỗi sử dụng: sửa khóa sau khi thêm vào `HashSet`/`HashMap`

Nếu một object thay đổi trường tham gia `equals` và `hashCode` sau khi được dùng làm khóa, vị trí tổ chức tra cứu trước đó có thể không còn phù hợp với mã băm mới. `contains` hoặc `get` có thể không tìm thấy khóa mà lập trình viên tưởng vẫn còn.

Đây là lý do nên dùng đối tượng khóa bất biến (*immutable*) hoặc ít nhất giữ các trường tham gia equality không đổi trong suốt thời gian khóa ở trong collection. Cần phân biệt: tính nhất quán của hash được Java yêu cầu **khi thông tin dùng để so sánh chưa đổi**; Java không cấm mọi object có trạng thái thay đổi.

### 7.4. Lỗi suy luận: nhầm cùng hash với bằng nhau

`a.hashCode() == b.hashCode()` chỉ nói hai kết quả số nguyên trùng nhau. Nó **không chứng minh** `a.equals(b)`. Trong mã nghiệp vụ, không được dùng mã băm như khóa định danh duy nhất hay thay cho phép so sánh giá trị đầy đủ nếu rủi ro trùng mã băm không được xử lý.

## 8. Những ranh giới thường bị nhầm với Object Contract

**`Comparable.compareTo` và `equals`:** `compareTo` thuộc interface `Comparable`, không phải phương thức của `Object`. Nên thiết kế thứ tự tự nhiên nhất quán với `equals` khi có thể, tức `compareTo(x) == 0` tương ứng với equality, đặc biệt khi muốn dùng `TreeSet`/`TreeMap`. Nhưng đây là **khuyến nghị** về tính nhất quán với equals, không phải yêu cầu phổ quát của `Object.equals`. Ví dụ `new BigDecimal("1.0").compareTo(new BigDecimal("1.00")) == 0` nhưng `equals` là `false` vì hai biểu diễn khác scale. Các collection sắp thứ tự có thể xem hai phần tử là cùng khóa dựa vào comparator dù `equals` của chúng khác nhau.

**Mảng trong đối tượng:** Mảng Java không tự so sánh nội dung phần tử bằng `Object.equals`; `Objects.equals(array1, array2)` vẫn sử dụng equality của mảng (thông thường là theo tham chiếu). Nếu equality mong muốn dựa trên nội dung mảng, phải chọn `Arrays.equals`/`Arrays.deepEquals` theo cấu trúc dữ liệu, đồng thời sử dụng cách tính hash tương ứng như `Arrays.hashCode`/`Arrays.deepHashCode`. Đây là yêu cầu nhất quán về **kết quả**, còn API trợ giúp cụ thể là lựa chọn triển khai.

**`record`:** Với Java 17, `record UserId(String value) {}` được trình biên dịch cung cấp sẵn `equals`, `hashCode` và `toString` theo record components. Đó là một cách giảm mã lặp cho kiểu dữ liệu phù hợp, không biến mọi class Java thành record và cũng không bắt class thông thường phải dùng đúng cùng mã nguồn thuật toán.

**Cấu trúc bên trong của collection:** API bảo đảm ngữ nghĩa của các thao tác công khai theo tài liệu. Số bucket, cách phân tán hash, thời điểm resize hoặc cách JVM lưu object có thể thay đổi theo cách triển khai. Không nên suy luận contract của chương trình từ một hình vẽ nội bộ `HashMap` ở một bản JDK cụ thể.

## 9. Cách tự xác định mức độ ràng buộc khi đọc tài liệu

Khi gặp một nhận định về đối tượng Java, hãy đi theo trình tự:

1. **Xác định nơi quy tắc được công bố.** Đó là Javadoc của `Object`, `Comparable`, class thư viện cụ thể hay chỉ là bài blog/đoạn code ví dụ?
2. **Tìm ngôn ngữ quy phạm.** “Must/shall”, tính chất được đặc tả và các điều kiện đi kèm là dấu hiệu hợp đồng; “recommended”, “typically”, “generally” thường là lời khuyên hoặc mô tả thường gặp. Không dựa độc nhất vào một từ mà bỏ qua ngữ cảnh.
3. **Viết phản ví dụ.** Nếu hai đối tượng khác nhau cùng hash, Java có sai không? Không. Nếu hai đối tượng equals nhau mà hash khác, có sai không? Có.
4. **Xem ai có thể thay đổi phần đó.** Nếu thay thuật toán hash, thứ tự bucket hoặc định dạng `toString` mà API vẫn giữ đúng cam kết, đó thường là lựa chọn triển khai. Nếu thay đổi làm `equals` mất đối xứng, đó là vi phạm contract.
5. **Kiểm tra điều kiện sử dụng.** Mã chạy trong Java 17, một thư viện cụ thể, kiểu mutable hay immutable? Điều kiện nào là giả định của ví dụ thay vì quy tắc phổ quát?

### Câu hỏi tự luyện

**Câu 1.** Hai đối tượng cùng hash nhưng `equals` trả `false`. Có vi phạm `Object` contract không?

**Đáp án:** Không. Va chạm hash được phép; chỉ chiều `equals` bằng nhau ⇒ hash bằng nhau là bắt buộc.

**Câu 2.** Một class override `equals` theo mã khách hàng, để nguyên `hashCode` kế thừa từ `Object`. Vì sao cần xem lại?

**Đáp án:** Hai instance khác nhau có thể bằng nhau theo mã khách hàng nhưng hash mặc định không được thiết kế bảo đảm phù hợp equality mới. Đây là nguy cơ vi phạm ràng buộc bắt buộc.

**Câu 3.** Một thư viện đổi định dạng `toString` trong phiên bản mới, nhưng trước đó không công bố định dạng là API. Ứng dụng parse `toString` bị lỗi. Lỗi thiết kế chính nằm ở đâu?

**Đáp án:** Ứng dụng đã phụ thuộc vào định dạng không được cam kết. Nên dùng API lấy dữ liệu có cấu trúc hoặc hợp đồng serialization riêng.

**Câu 4.** Một thuật toán `hashCode` trả hằng số `1` có sai về contract không?

**Đáp án:** Không, nhưng phân bố kém và có thể khiến collection xử lý va chạm nhiều hơn.

## 10. Ghi nhớ

- **Bắt buộc:** các tính chất của `equals`; `equals` bằng nhau thì `hashCode` bằng nhau; hash nhất quán khi dữ liệu dùng trong equality chưa đổi.
- **Quy ước tốt:** equality/hash dựa trên dữ liệu có ý nghĩa, ưu tiên khóa bất biến, `toString` dễ hiểu và an toàn khi log, cân nhắc tính nhất quán giữa ordering và equality.
- **Chi tiết triển khai:** hệ số tính hash, cách kết hợp trường, dữ liệu nội bộ của hash collection, cách JVM sinh identity hash, định dạng `toString` do class tự quyết nếu không có cam kết cụ thể.
- **Không suy luận ngược:** cùng hash không có nghĩa là equals; thứ tự duyệt collection không mặc nhiên là thứ tự chèn; mã chạy thành công không tự chứng minh contract đã đúng.

Tài liệu API gốc để đối chiếu: [`Object` (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html), [`Comparable` (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Comparable.html) và [`HashMap` (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html).
