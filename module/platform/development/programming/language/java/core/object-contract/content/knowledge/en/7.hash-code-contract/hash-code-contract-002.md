# Hai đối tượng `equals()` phải có cùng hash code

## 1. Quy tắc bắt buộc của hợp đồng `hashCode()`

Trong Java, nếu hai đối tượng được xem là bằng nhau theo `equals()` thì **giá trị `hashCode()` của chúng phải bằng nhau**. Với hai tham chiếu khác `null` là `a` và `b`:

~~~text
a.equals(b) == true  =>  a.hashCode() == b.hashCode()
~~~

Dấu `=>` thể hiện quan hệ kéo theo trong logic, không phải toán tử Java. Đây là quy tắc của **hợp đồng `Object.hashCode()`**. Nó áp dụng khi hai tham chiếu chỉ đến cùng một đối tượng, và quan trọng hơn, cả khi hai đối tượng **riêng biệt** được lớp của chúng coi là bằng nhau theo dữ liệu.

**Không được đảo chiều quy tắc:**

~~~text
a.hashCode() == b.hashCode()  không suy ra  a.equals(b) == true
~~~

Hai đối tượng có thể nhận cùng mã băm nhưng `equals()` trả về `false`. Điều này gọi là **va chạm băm** (*hash collision*) và hoàn toàn hợp lệ. `hashCode()` trả về một số nguyên `int` 32 bit, không thể gán một mã duy nhất cho tất cả giá trị và đối tượng có thể tồn tại.

Ba trường hợp cần phân biệt:

- `a.equals(b) == true`: **bắt buộc** hai mã băm bằng nhau.
- `a.equals(b) == false`: mã băm có thể bằng hoặc khác nhau.
- `a == b`: hai biến trỏ cùng một thể hiện; nếu trạng thái quyết định `equals()` không thay đổi, các lần gọi `hashCode()` phải nhất quán.

Ví dụ, nếu lớp `CustomerKey` xác định hai khách hàng bằng cùng `customerId`, hai đối tượng `new CustomerKey("C1")` riêng biệt phải trả về cùng mã băm khi `equals()` trả về `true`. Chúng không nhất thiết là cùng một đối tượng trong bộ nhớ.

## 2. Ba phần của hợp đồng `Object.hashCode()`

1. **Nhất quán trong một lần thực thi.** Gọi `hashCode()` nhiều lần trên một đối tượng phải cho cùng kết quả trong chừng mực dữ liệu tham gia `equals()` không đổi. Không có cam kết mã băm phải giữ nguyên giữa hai lần chạy ứng dụng.
2. **Bằng nhau thì cùng mã băm.** Nếu `a.equals(b)` là `true`, hai lời gọi `a.hashCode()` và `b.hashCode()` phải trả về cùng `int`.
3. **Không bằng nhau vẫn được phép trùng mã băm.** Không bắt buộc hai đối tượng khác nhau theo `equals()` phải có mã băm khác nhau. Một hàm băm phân bố tốt giúp giảm va chạm và cải thiện hiệu năng, nhưng tính duy nhất không phải yêu cầu của hợp đồng.

Bên cạnh đó, `equals()` cần tuân thủ tính **phản xạ** (`a.equals(a)`), **đối xứng** (nếu `a.equals(b)` thì `b.equals(a)`), **bắc cầu**, **nhất quán**, và `a.equals(null)` là `false` với `a` khác `null`. Mã băm chỉ có ý nghĩa ổn định khi định nghĩa “hai đối tượng bằng nhau” cũng nhất quán.

> Quy tắc thực hành: **Ghi đè `equals()` để so sánh theo giá trị thì phải ghi đè `hashCode()` tương ứng.** Dựa hai phương thức trên cùng khái niệm “bằng nhau”.

## 3. Vì sao các cấu trúc băm phụ thuộc quy tắc này?

`HashMap` và `HashSet` dùng mã băm để định hướng nơi tra cứu các khóa hoặc phần tử, rồi kiểm tra tính bằng nhau khi cần phân biệt các ứng viên. Có thể hình dung:

1. Thêm đối tượng `a`: cấu trúc tính `a.hashCode()` và chọn vùng lưu trữ ứng viên.
2. Tra cứu bằng đối tượng `b` mà `b.equals(a) == true`: cấu trúc tính `b.hashCode()` để tìm đúng nơi có ứng viên tương ứng.
3. Nếu mã băm của `a` và `b` không tương thích, phép tra cứu có thể đi sai vùng, không bao giờ so sánh hai đối tượng với nhau, dù `equals()` nói rằng chúng bằng nhau.
4. Nếu hai mã băm bằng nhau nhưng `equals()` khác nhau, cấu trúc vẫn có thể giữ hai khóa. Đây là tình huống va chạm bình thường.

Đó là mô hình khái niệm; `HashMap` có thể xử lý hoặc trộn các bit của mã băm và dùng các cấu trúc khác nhau bên trong. Hợp đồng của khóa quan trọng hơn chi tiết triển khai.

Vi phạm quy tắc bằng nhau ⇒ cùng mã băm có thể dẫn đến `HashSet.contains(b)` trả về `false` dù `a` tương đương đã được thêm, hoặc `HashMap.get(b)` không tìm được giá trị lưu dưới `a`. Không nên khẳng định một lần tra cứu cụ thể chắc chắn thất bại trên mọi JVM, bởi cách bố trí vùng băm và khả năng va chạm ảnh hưởng biểu hiện; lỗi cốt lõi là **không bảo đảm đúng hợp đồng**.

## 4. Ví dụ Java 17+ biên dịch và chạy được

Lớp `AccountId` trong ví dụ có một trường `value` bất biến. Cả `equals()` và `hashCode()` đều sử dụng cùng giá trị, nên hai đối tượng khác tham chiếu nhưng cùng tài khoản được công nhận là một khóa logic.

Tạo tệp `HashContractDemo.java`:

~~~java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class HashContractDemo {
    static final class AccountId {
        private final String value;

        AccountId(String value) {
            this.value = Objects.requireNonNull(value);
        }

        @Override
        public boolean equals(Object other) {
            return this == other
                    || (other instanceof AccountId id
                        && value.equals(id.value));
        }

        @Override
        public int hashCode() {
            return value.hashCode();
        }
    }

    public static void main(String[] args) {
        AccountId first = new AccountId("ACC-100");
        AccountId equivalent = new AccountId("ACC-100");
        AccountId different = new AccountId("ACC-200");

        System.out.println("same reference: "
                + (first == equivalent));
        System.out.println("equal values: "
                + first.equals(equivalent));
        System.out.println("equal objects have same hash: "
                + (first.hashCode() == equivalent.hashCode()));
        System.out.println("different values: "
                + first.equals(different));

        Set<AccountId> ids = new HashSet<>();
        System.out.println("add first: " + ids.add(first));
        System.out.println("contains equivalent: "
                + ids.contains(equivalent));
        System.out.println("add equivalent: "
                + ids.add(equivalent));
        System.out.println("set size: " + ids.size());

        Map<AccountId, String> owners = new HashMap<>();
        owners.put(first, "Linh");
        System.out.println("lookup with equivalent: "
                + owners.get(equivalent));

        System.out.println("Aa equals BB: " + "Aa".equals("BB"));
        System.out.println("Aa and BB same hash: "
                + ("Aa".hashCode() == "BB".hashCode()));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac HashContractDemo.java
java HashContractDemo
~~~

**Kết quả đầu ra xác định:**

~~~text
same reference: false
equal values: true
equal objects have same hash: true
different values: false
add first: true
contains equivalent: true
add equivalent: false
set size: 1
lookup with equivalent: Linh
Aa equals BB: false
Aa and BB same hash: true
~~~

**Giải thích kết quả:**

- `first` và `equivalent` là hai đối tượng từ hai lệnh `new` khác nhau, nên `first == equivalent` là `false`. Chúng mang cùng `value`, nên `first.equals(equivalent)` là `true`.
- Hai phương thức `hashCode()` dùng cùng giá trị chuỗi `"ACC-100"`; kết quả băm phải bằng nhau. Không cần in con số cụ thể để kiểm tra hợp đồng.
- `HashSet` thêm `first` thành công, tìm thấy khóa tương đương bằng `contains(equivalent)`, và từ chối thêm khóa tương đương lần nữa. Kích thước còn `1`.
- `HashMap` lấy ra `"Linh"` bằng một đối tượng khóa khác tham chiếu nhưng cùng giá trị logic.
- `"Aa"` và `"BB"` không bằng nhau theo `String.equals()`, tuy nhiên `String.hashCode()` của cả hai là `2112`. Đây là va chạm được phép, chứng minh không được suy ra `equals() == true` chỉ từ việc băm bằng nhau.

## 5. Lỗi thường gặp: ghi đè `equals()` nhưng quên `hashCode()`

Ví dụ **đoạn mã minh họa** sau chỉ ghi đè `equals()`, không phải một chương trình độc lập:

~~~java
final class BrokenKey {
    private final String code;

    BrokenKey(String code) {
        this.code = code;
    }

    @Override
    public boolean equals(Object other) {
        return this == other
                || (other instanceof BrokenKey key
                    && java.util.Objects.equals(code, key.code));
    }

    // Thiếu hashCode(): vẫn kế thừa Object.hashCode().
}
~~~

Hai đối tượng `new BrokenKey("A")` khác nhau có `equals() == true`, nhưng `Object.hashCode()` mặc định gắn với danh tính nên **không có bảo đảm** mã băm của chúng bằng nhau. Do đó lớp này không thỏa mãn hợp đồng cần thiết của các tập hợp theo băm.

Không thể mặc định khẳng định mỗi cặp đối tượng khác nhau luôn có mã băm danh tính khác nhau; va chạm vẫn có thể xảy ra. Lỗi là việc triển khai **không bảo đảm** mệnh đề “bằng nhau thì có mã băm bằng nhau”.

Cách sửa là ghi đè thêm `hashCode()` để sử dụng cùng trường `code`:

~~~java
@Override
public int hashCode() {
    return java.util.Objects.hashCode(code);
}
~~~

Đây là **phương thức bổ sung cho lớp `BrokenKey`**, không phải mã chạy độc lập. `Objects.hashCode(code)` trả về `0` nếu `code` là `null`, và nếu khác `null` thì sử dụng `code.hashCode()`. Cơ chế này tương thích với `Objects.equals(code, key.code)` trong phương thức `equals()` bên trên.

## 6. Chọn trường nào để viết `hashCode()`?

Hãy bắt đầu từ định nghĩa `equals()`. Ví dụ, giả sử đối tượng khóa được xác định bởi **cặp** `tenantId` và `orderNumber`. Một thiết kế tương thích thường so sánh đúng hai trường trong `equals()` và kết hợp chúng trong `hashCode()`.

Đây là **cặp phương thức minh họa**, giả định nằm trong lớp `OrderKey` có hai trường nêu trên và đã import `java.util.Objects`:

~~~java
@Override
public boolean equals(Object other) {
    return this == other
            || (other instanceof OrderKey key
                && Objects.equals(tenantId, key.tenantId)
                && Objects.equals(orderNumber, key.orderNumber));
}

@Override
public int hashCode() {
    return Objects.hash(tenantId, orderNumber);
}
~~~

Vì hai khóa có cùng `tenantId` và `orderNumber` sẽ sinh cùng mã băm, điều kiện hợp đồng được đáp ứng. `Objects.hash(...)` **không bảo đảm** tạo mã khác nhau cho mọi cặp giá trị; va chạm vẫn hợp lệ.

**Một sắc thái quan trọng:** Không phải cứ bỏ bớt một trường khỏi `hashCode()` là vi phạm hợp đồng. Nếu `equals()` so sánh hai trường và `hashCode()` chỉ trả mã băm từ trường thứ nhất, mọi cặp bằng nhau vẫn có trường thứ nhất bằng nhau và vì thế có mã băm bằng nhau. Vấn đề ở đây là **phân bố băm kém**, có thể làm giảm hiệu năng. Ngược lại, nếu `hashCode()` dựa vào trường thay đổi độc lập mà `equals()` không xét, hai đối tượng bằng nhau có thể cho mã băm khác nhau: đó là lỗi đúng/sai về hợp đồng.

### Thận trọng với đối tượng có thể thay đổi

Ngay cả khi `equals()` và `hashCode()` dùng đúng các trường, việc thay đổi những trường đó khi đối tượng đang làm khóa của `HashMap` hoặc phần tử trong `HashSet` vẫn có thể gây lỗi tra cứu. Khóa được lưu theo mã băm cũ; sau khi giá trị thay đổi, tìm bằng mã băm mới có thể không tìm thấy nó.

Do đó, nên ưu tiên **khóa bất biến**: trường `final`, dữ liệu bên trong cũng không thay đổi theo cách ảnh hưởng đến `equals()`. Một trường tham chiếu khai báo `final` nhưng trỏ đến cấu trúc dữ liệu có thể sửa vẫn cần được xem xét.

### Kiểu dữ liệu có sẵn

- `String`, `Integer`, `Long` và nhiều kiểu giá trị chuẩn đã triển khai `equals()`/`hashCode()` nhất quán.
- `record` trong Java hiện đại tự sinh `equals()` và `hashCode()` dựa trên các thành phần; cần cân nhắc nếu thành phần chứa dữ liệu có thể thay đổi.
- Mảng trong Java mặc định kế thừa so sánh theo danh tính từ `Object`. Nếu muốn so sánh theo nội dung mảng, dùng cặp `Arrays.equals(...)` và `Arrays.hashCode(...)` tương ứng; với mảng lồng nhau có `Arrays.deepEquals(...)` và `Arrays.deepHashCode(...)`.
- Với lớp có kế thừa, thiết kế `equals()` giữa lớp cha và lớp con cần bảo đảm tính đối xứng và bắc cầu. Lỗi này cũng có thể ảnh hưởng đến hợp đồng `hashCode()`.

## 7. Phân biệt các nhận định dễ nhầm

| Nhận định | Kết luận | Giải thích |
| --- | --- | --- |
| `a.equals(b)` đúng ⇒ mã băm bằng nhau | **Bắt buộc** | Hợp đồng `Object.hashCode()` |
| Mã băm bằng nhau ⇒ `a.equals(b)` đúng | **Sai** | Va chạm băm được phép |
| `a.equals(b)` sai ⇒ mã băm phải khác nhau | **Sai** | Không có điều kiện bắt buộc này |
| `a == b` ⇒ mã băm nhất quán nếu dữ liệu liên quan không đổi | **Đúng** | Cùng một đối tượng |
| `a.equals(b)` đúng ⇒ `a == b` | **Sai** | Hai thể hiện riêng có thể bằng nhau theo giá trị |
| Mọi `hashCode()` trả về một hằng số là vi phạm | **Sai** | Hợp đồng có thể đúng nhưng rất nhiều va chạm |
| Ghi đè `equals()` theo giá trị rồi giữ `Object.hashCode()` luôn an toàn | **Sai** | Không bảo đảm mã băm bằng nhau cho hai thể hiện tương đương |
| Mã băm danh tính `System.identityHashCode()` phải giống nhau cho hai đối tượng `equals()` | **Sai** | Nó phản ánh danh tính, không theo tính bằng nhau của giá trị |

Hàm `hashCode()` luôn trả về `0` cho mọi đối tượng có thể đáp ứng điều kiện **bằng nhau ⇒ cùng mã băm**, nhưng sẽ phân bố rất kém và giảm hiệu năng bảng băm. Một mã băm phức tạp phân bố tốt nhưng không tương thích với `equals()` mới là lỗi hợp đồng.

## 8. Checklist triển khai và kiểm thử

1. Định nghĩa rõ “bằng nhau”: dựa trên những thuộc tính nào, có thể có hai thể hiện khác nhau nhưng tương đương hay không?
2. Triển khai `equals()` phản xạ, đối xứng, bắc cầu, nhất quán, và xử lý `null` đúng.
3. Triển khai `hashCode()` từ các giá trị tương thích với `equals()`. Với nhiều trường, cân nhắc `Objects.hash(...)` hoặc kết hợp băm có kiểm soát.
4. Tạo hai thể hiện **khác nhau về tham chiếu nhưng bằng nhau theo `equals()`**, và xác nhận hai mã băm bằng nhau.
5. Kiểm tra trường hợp hai giá trị khác nhau nhưng mã băm trùng; cấu trúc băm vẫn phải phân biệt bằng `equals()`.
6. Kiểm tra `HashSet.add`/`contains` và `HashMap.put`/`get` bằng các thể hiện khóa tương đương.
7. Giữ ổn định các trường quyết định `equals()`/`hashCode()` trong suốt thời gian khóa nằm trong cấu trúc băm.

## 9. Tự kiểm tra

**Câu 1.** Hai thể hiện `new String("java")` khác nhau có `equals()` bằng `true`. Mã băm của chúng có bắt buộc bằng nhau?

**Đáp án:** Có. `String.hashCode()` dựa trên nội dung chuỗi. Hai đối tượng vẫn có thể khác tham chiếu.

**Câu 2.** `"Aa"` và `"BB"` cùng mã băm. Có phải Java vi phạm hợp đồng?

**Đáp án:** Không. Hai chuỗi không bằng nhau, nên việc mã băm trùng hoàn toàn hợp lệ.

**Câu 3.** Nếu `equals()` chỉ so sánh `id` nhưng `hashCode()` lấy mã tạo ngẫu nhiên riêng cho từng thể hiện, điều gì sai?

**Đáp án:** Hai thể hiện có cùng `id` có thể `equals() == true` nhưng trả về mã băm khác nhau, vi phạm hợp đồng và có thể khiến phép tra cứu dựa trên băm sai.

**Câu 4.** Hai khóa khác nhau có mã băm bằng nhau có tự động bị `HashSet` gộp làm một không?

**Đáp án:** Không. Mã băm giúp định hướng tra cứu; cấu trúc còn phải xét tính bằng nhau để phân biệt các khóa va chạm.

**Ghi nhớ:** `equals()` bằng nhau **bắt buộc** `hashCode()` bằng nhau. Mã băm bằng nhau **không chứng minh** hai đối tượng bằng nhau. Thiết kế hai phương thức nhất quán là điều kiện quan trọng để dùng đúng `HashMap` và `HashSet`.
