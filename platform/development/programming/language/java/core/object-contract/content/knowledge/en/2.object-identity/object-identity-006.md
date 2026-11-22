# `System.identityHashCode()` bỏ qua `hashCode()` được ghi đè

## 1. Bản chất của identity hash code

`System.identityHashCode(Object x)` trả về **mã băm theo danh tính đối tượng** (*identity hash code*): mã băm mà cách cài đặt mặc định của `Object.hashCode()` sẽ trả về đối với chính đối tượng đó, **bất kể lớp đã ghi đè `hashCode()` hay chưa**.

Hãy phân biệt các thao tác:

- `x.hashCode()` là lời gọi đa hình: nó chạy `hashCode()` ghi đè nếu lớp của `x` có định nghĩa lại phương thức.
- `System.identityHashCode(x)` là phương thức `static` của `System`; nó **bỏ qua** phiên bản `hashCode()` ghi đè.
- `x == y` kiểm tra hai biến tham chiếu có trỏ đến **cùng một đối tượng** hay không.
- `x.equals(y)` kiểm tra tính bằng nhau theo định nghĩa `equals()`, thường dựa trên dữ liệu hoặc trạng thái.
- `System.identityHashCode(null)` được định nghĩa trả về `0`.

Danh tính khác với tính bằng nhau theo giá trị: hai đối tượng có cùng dữ liệu có thể `equals() == true`, nhưng `==` vẫn là `false` nếu chúng được tạo riêng. Mã băm danh tính là dấu hiệu phục vụ xử lý theo tham chiếu, **không phải mã định danh duy nhất**.

## 2. So sánh các biểu thức liên quan

| Biểu thức | Cơ chế | Có gọi `hashCode()` ghi đè? |
| --- | --- | --- |
| `x.hashCode()` | Gọi phương thức của lớp theo cơ chế đa hình | **Có**, nếu lớp ghi đè |
| `System.identityHashCode(x)` | Lấy mã băm mặc định theo danh tính | **Không** |
| `Objects.hashCode(x)` | `0` nếu `x == null`; ngược lại gọi `x.hashCode()` | **Có**, nếu lớp ghi đè |
| `x == y` | So sánh hai tham chiếu | Không dùng mã băm |
| `x.equals(y)` | So sánh theo quy tắc của lớp | Không mặc nhiên dùng mã băm |

Nếu lớp **không ghi đè** `hashCode()`, `x.hashCode()` sử dụng mặc định của `Object` và nhận cùng giá trị như `System.identityHashCode(x)`. Nếu lớp **đã ghi đè**, hai giá trị có thể khác nhau, nhưng cũng có thể tình cờ trùng nhau. Sự trùng số không có nghĩa là `identityHashCode` gọi phương thức ghi đè.

## 3. Ví dụ Java 17+ chạy độc lập

Chương trình dưới đây dùng bộ đếm trong `hashCode()` để quan sát xem phương thức ghi đè có được gọi hay không. Đây chỉ là công cụ chứng minh cho bài học; trong ứng dụng thật, nên tránh để `hashCode()` phát sinh tác dụng phụ.

Lưu thành tệp `IdentityHashDemo.java`:

~~~java
import java.util.HashMap;
import java.util.IdentityHashMap;
import java.util.Map;

public class IdentityHashDemo {
    static final class Key {
        private final int id;
        private int hashCodeCalls;

        Key(int id) {
            this.id = id;
        }

        @Override
        public boolean equals(Object other) {
            return this == other
                    || (other instanceof Key key && id == key.id);
        }

        @Override
        public int hashCode() {
            hashCodeCalls++;
            return 42; // Cố tình trả về hằng số để minh họa.
        }
    }

    public static void main(String[] args) {
        Key first = new Key(10);
        Key alias = first;
        Key second = new Key(10);

        System.out.println("first.equals(second) = "
                + first.equals(second));
        System.out.println("first == second = " + (first == second));

        int firstIdentityHash = System.identityHashCode(first);
        System.out.println("calls after identityHashCode = "
                + first.hashCodeCalls);

        System.out.println("first.hashCode() = " + first.hashCode());
        System.out.println("calls after hashCode = "
                + first.hashCodeCalls);

        System.out.println("alias has same identity hash = "
                + (firstIdentityHash == System.identityHashCode(alias)));
        System.out.println("identityHashCode(null) = "
                + System.identityHashCode(null));

        Map<Key, String> byValue = new HashMap<>();
        byValue.put(first, "first");
        byValue.put(second, "second");

        Map<Key, String> byIdentity = new IdentityHashMap<>();
        byIdentity.put(first, "first");
        byIdentity.put(second, "second");

        System.out.println("HashMap size = " + byValue.size());
        System.out.println("IdentityHashMap size = "
                + byIdentity.size());
    }
}
~~~

Biên dịch và chạy từ thư mục chứa tệp bằng JDK 17 trở lên:

~~~bash
javac IdentityHashDemo.java
java IdentityHashDemo
~~~

Kết quả đầu ra xác định:

~~~text
first.equals(second) = true
first == second = false
calls after identityHashCode = 0
first.hashCode() = 42
calls after hashCode = 1
alias has same identity hash = true
identityHashCode(null) = 0
HashMap size = 1
IdentityHashMap size = 2
~~~

**Giải thích từng phần:**

1. Hai lệnh `new Key(10)` tạo hai đối tượng khác nhau. Vì `equals()` so sánh `id`, `first.equals(second)` là `true` trong khi `first == second` là `false`.
2. `System.identityHashCode(first)` không làm tăng `hashCodeCalls`: bộ đếm vẫn bằng `0`, chứng minh phiên bản `hashCode()` ghi đè không được gọi.
3. Sau lời gọi trực tiếp `first.hashCode()`, bộ đếm tăng lên `1`, và giá trị của phương thức ghi đè là `42`.
4. `alias` chỉ là tham chiếu khác đến chính `first`; cùng một đối tượng phải nhận cùng mã băm danh tính trong một lần chạy.
5. `HashMap` dựa trên `equals()` và `hashCode()` thông thường nên xem `first` và `second` là một khóa logic: kích thước bằng `1`.
6. `IdentityHashMap` so sánh khóa bằng `==` và dùng cơ chế băm theo danh tính, nên giữ **hai khóa**: kích thước bằng `2`. Điều này vẫn đúng ngay cả khi mã băm danh tính của hai khóa tình cờ va chạm.

Chương trình chủ động không in trực tiếp các con số `System.identityHashCode(first)` và `System.identityHashCode(second)`, vì chúng phụ thuộc vào JVM và không có đầu ra số cố định cần ghi nhớ.

## 4. Quan hệ với hợp đồng `equals()`/`hashCode()`

Hợp đồng của `Object.hashCode()` quy định: khi hai đối tượng `a` và `b` bằng nhau theo `a.equals(b)`, `a.hashCode()` và `b.hashCode()` **phải bằng nhau**. Chiều ngược lại không đúng: hai đối tượng có cùng mã băm vẫn có thể không bằng nhau. Giá trị băm được kỳ vọng giữ ổn định trong một lần chạy khi thông tin dùng cho `equals()` không thay đổi.

Quy tắc “`equals()` bằng nhau ⇒ `hashCode()` bằng nhau” áp dụng cho `hashCode()` phục vụ bình đẳng theo giá trị, **không áp đặt** lên `System.identityHashCode()` của hai đối tượng riêng biệt. Hai đối tượng `equals() == true` có thể nhận identity hash code khác nhau; cũng có thể va chạm nên bằng nhau.

Nếu một lớp ghi đè `equals()` để so sánh theo giá trị, cần ghi đè `hashCode()` tương thích khi sử dụng lớp làm khóa của `HashMap` hoặc phần tử `HashSet`. Không lấy `System.identityHashCode(this)` để cài đặt `hashCode()` cho kiểu có ngữ nghĩa bình đẳng theo giá trị: các đối tượng `equals()` bằng nhau khi đó có thể trả về mã băm khác, làm hỏng hợp đồng.

## 5. Các tình huống sử dụng phù hợp

**Gỡ lỗi danh tính đối tượng.** Khi `hashCode()` hay `toString()` đã được ghi đè để hiển thị dữ liệu nghiệp vụ, có thể ghi nhận mã băm danh tính giúp quan sát thể hiện đối tượng cụ thể:

~~~java
static String debugTag(Object obj) {
    if (obj == null) {
        return "null";
    }
    return obj.getClass().getName() + "@"
            + Integer.toHexString(System.identityHashCode(obj));
}
~~~

Đây là **đoạn mã minh họa**, đặt vào bên trong một lớp thích hợp nếu muốn sử dụng. Dạng `TênLớp@hex` hữu ích cho log, nhưng không đảm bảo duy nhất: hai đối tượng có thể trùng mã băm. Nó cũng không cung cấp vị trí bộ nhớ.

**Cấu trúc tra cứu theo tham chiếu.** `IdentityHashMap` phù hợp cho những bài toán cần phân biệt từng thể hiện, như ghi nhận các đối tượng đã duyệt trong đồ thị có vòng tham chiếu hoặc quản lý trạng thái gắn với chính đối tượng. `HashMap` phù hợp hơn nếu khóa đại diện cho cùng giá trị nghiệp vụ.

**So sánh danh tính thật sự.** Khi cần câu trả lời chính xác “có cùng đối tượng không?”, dùng `==` đối với hai tham chiếu; nếu dùng tập hợp theo danh tính, dựa trên ngữ nghĩa của `IdentityHashMap`. Không suy luận danh tính từ việc so sánh hai số `identityHashCode`.

## 6. Giới hạn và lỗi thường gặp

- **Không phải địa chỉ bộ nhớ.** API chỉ trả về một số nguyên `int` theo danh tính. Không có cam kết đó là con trỏ, địa chỉ heap hay vị trí vật lý của đối tượng.
- **Không bảo đảm duy nhất.** Hai đối tượng khác nhau có thể cho cùng số nguyên `identityHashCode` (*hash collision*). So sánh mã băm bằng nhau không thay thế được `==`.
- **Không có ID bền vững qua lần chạy.** Không lưu identity hash code làm khóa cơ sở dữ liệu, mã người dùng, UUID hay mã liên thông các JVM; giá trị không được bảo đảm ổn định giữa các tiến trình hoặc lần khởi động.
- **Không nhầm với `Objects.hashCode(x)`.** `Objects.hashCode(x)` gọi `x.hashCode()` khi `x` khác `null`, tức vẫn đi qua override. Cả hai trả về `0` đối với `null`, nhưng cơ chế cho đối tượng khác `null` khác nhau.
- **Không nhầm với `Object.toString()`.** Cài đặt mặc định của `Object.toString()` thường gồm tên lớp và dạng hex của mã băm, nhưng `toString()` cũng có thể được ghi đè; muốn chủ động lấy mã băm danh tính thì gọi `System.identityHashCode(x)`.
- **Không cho rằng “cùng số ⇒ cùng đối tượng” hay “khác đối tượng ⇒ khác số”.** Cả hai suy luận đều sai vì va chạm băm. Khi cần danh tính chính xác, chọn `==`.
- **Không cho rằng override phải cho kết quả khác identity hash.** Một `hashCode()` ghi đè có thể tình cờ trả đúng giá trị mã băm danh tính. Cơ chế gọi phương thức không được xác định bằng phép so sánh hai số.
- **Không sao chép bộ đếm trong ví dụ vào ứng dụng thực tế.** Bộ đếm chỉ để thấy luồng thực thi; `hashCode()` sản xuất nên tránh tác dụng phụ và giữ nhất quán với `equals()`.

## 7. Câu hỏi tự kiểm tra

**1.** Một lớp ghi đè `hashCode()` luôn trả về `7`. `System.identityHashCode(x)` có bắt buộc bằng `7`?

Không. Nó bỏ qua override; kết quả có thể tình cờ bằng `7` nhưng không có yêu cầu đó.

**2.** `a.equals(b) == true` có bắt buộc `System.identityHashCode(a) == System.identityHashCode(b)`?

Không. Quy tắc hai đối tượng bằng nhau phải có cùng mã băm áp dụng cho `hashCode()` thông thường; `identityHashCode` theo danh tính riêng của từng thể hiện.

**3.** Hai đối tượng có `System.identityHashCode` bằng nhau, liệu `a == b` phải là `true`?

Không. Identity hash code có thể va chạm. Hãy dùng `==`.

**4.** Lựa chọn nào phù hợp khi cần theo dõi từng đối tượng riêng, kể cả khi `equals()` của chúng bằng nhau?

`IdentityHashMap` là lựa chọn chuyên biệt cho khóa so sánh theo tham chiếu; `HashMap` phục vụ ngữ nghĩa bằng nhau theo giá trị.

**Ghi nhớ:** `System.identityHashCode(x)` luôn bỏ qua `hashCode()` ghi đè để lấy mã băm mặc định theo danh tính; **danh tính chính xác được kiểm tra bằng `==`, không bằng cách so sánh các mã băm**.
