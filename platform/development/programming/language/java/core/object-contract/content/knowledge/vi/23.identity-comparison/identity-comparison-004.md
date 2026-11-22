# Phân biệt identity hash code với mã duy nhất trong Java

## 1. Vấn đề: cùng một đối tượng hay cùng một mã?

Trong Java, **danh tính đối tượng** (*object identity*) trả lời câu hỏi «hai biến có đang trỏ tới chính cùng một instance trong JVM không?». Trong khi đó, **bằng nhau về giá trị** (*value equality*) trả lời câu hỏi «hai đối tượng có được xem là tương đương theo quy tắc nghiệp vụ hoặc trạng thái không?». **Identity hash code** chỉ là một số băm liên quan tới danh tính đối tượng; nó **không phải mã định danh duy nhất**.

Ví dụ, hai đối tượng `Person` khác nhau có thể cùng tên, cùng mã khách hàng và được `equals()` đánh giá bằng nhau; chúng vẫn là hai instance riêng. Ngược lại, hai biến trỏ đến cùng một instance luôn có cùng danh tính, bất kể dữ liệu của instance ấy thay đổi.

## 2. Phân biệt các công cụ

| Công cụ | Trả lời câu hỏi gì? | Điểm cần nhớ |
| --- | --- | --- |
| `a == b` (với biến tham chiếu) | Có cùng một đối tượng không? | So sánh tham chiếu, là phép kiểm tra identity trực tiếp. |
| `a.equals(b)` | Có bằng nhau theo quy tắc của lớp không? | Có thể được override để so sánh giá trị; `Object.equals()` mặc định dùng identity. |
| `a.hashCode()` | Giá trị băm mà lớp cung cấp là gì? | Có thể override; phục vụ cấu trúc băm, chịu hợp đồng `equals()`/`hashCode()`. |
| `System.identityHashCode(a)` | Mã băm theo cách mặc định của `Object` là gì? | Bỏ qua mọi override của `hashCode()`; trả về `int`, có thể trùng. |
| ID nghiệp vụ hoặc ID lưu trữ | Có thể tham chiếu thực thể nào qua thời gian/hệ thống? | Phải được thiết kế và kiểm soát tính duy nhất, ví dụ khóa chính DB/UUID. |

`System.identityHashCode(x)` trả về giá trị mà cách cài đặt mặc định của `Object.hashCode()` sẽ trả về cho đối tượng đó, **kể cả khi lớp đã override `hashCode()`**. Với `x == null`, phương thức trả về `0`. Còn `Objects.hashCode(x)` (nếu dùng) gọi `x.hashCode()` khi `x` khác `null`, nên không thay thế cho identity hash code.

### Tính chất logic quan trọng

- Nếu `a == b` thì `System.identityHashCode(a) == System.identityHashCode(b)`.
- Nếu hai identity hash code **khác nhau** trong cùng lần thực thi thì hai tham chiếu không thể trỏ tới cùng một đối tượng.
- Nếu hai identity hash code **bằng nhau**, **không được kết luận** `a == b`: các đối tượng khác nhau vẫn có thể va chạm băm (*collision*).
- Nếu `a.equals(b)` là `true`, hợp đồng `hashCode()` buộc `a.hashCode() == b.hashCode()`, nhưng **không bắt buộc** hai identity hash code bằng nhau.
- Nếu `a.hashCode() == b.hashCode()` thì chưa đủ để kết luận `a.equals(b)` hay `a == b`.

Identity hash code có kiểu `int` (32 bit, tức tối đa `2^32` mẫu bit), nên không thể bảo đảm một giá trị riêng cho mọi đối tượng trong mọi tình huống. Đặc tả Java chỉ hướng đến việc các instance khác nhau nhận mã băm khác nhau **trong mức độ khả thi hợp lý**, chứ không cam kết không va chạm. Không được coi con số này là địa chỉ bộ nhớ, số thứ tự tạo đối tượng hoặc ID bền vững: JVM có quyền chọn cách tính, GC có thể di chuyển đối tượng, và giá trị không có cam kết ổn định giữa các lần chạy hay giữa các JVM.

## 3. Ví dụ chạy được với Java 17+

Lớp `Ticket` chủ ý định nghĩa bằng nhau theo `code`, nên hai instance khác nhau vẫn `equals()` bằng nhau. Ta đối chiếu `HashMap` (dựa vào `equals()`/`hashCode()`) với `IdentityHashMap` (dựa vào `==` và identity hash code).

```java
import java.util.HashMap;
import java.util.IdentityHashMap;
import java.util.Map;

public class IdentityHashCodeDemo {
    static final class Ticket {
        private final String code;

        Ticket(String code) {
            this.code = code;
        }

        @Override
        public boolean equals(Object other) {
            return this == other
                    || (other instanceof Ticket ticket && code.equals(ticket.code));
        }

        @Override
        public int hashCode() {
            return code.hashCode();
        }
    }

    public static void main(String[] args) {
        Ticket first = new Ticket("T-01");
        Ticket second = new Ticket("T-01");
        Ticket alias = first;

        System.out.println("first == second: " + (first == second));
        System.out.println("first.equals(second): " + first.equals(second));
        System.out.println("first == alias: " + (first == alias));
        System.out.println("value hashes equal: "
                + (first.hashCode() == second.hashCode()));
        System.out.println("alias identity hashes equal: "
                + (System.identityHashCode(first) == System.identityHashCode(alias)));

        Map<Ticket, String> byValue = new HashMap<>();
        byValue.put(first, "one");
        byValue.put(second, "two");

        Map<Ticket, String> byIdentity = new IdentityHashMap<>();
        byIdentity.put(first, "one");
        byIdentity.put(second, "two");

        System.out.println("HashMap size: " + byValue.size());
        System.out.println("IdentityHashMap size: " + byIdentity.size());
        System.out.println("identityHashCode(null): " + System.identityHashCode(null));
    }
}
```

Lưu tệp `IdentityHashCodeDemo.java`, biên dịch và chạy:

```bash
javac -encoding UTF-8 IdentityHashCodeDemo.java
java IdentityHashCodeDemo
```

Đầu ra xác định:

```text
first == second: false
first.equals(second): true
first == alias: true
value hashes equal: true
alias identity hashes equal: true
HashMap size: 1
IdentityHashMap size: 2
identityHashCode(null): 0
```

**Giải thích:** `first` và `second` là hai đối tượng khác nhau dù cùng `code`; vì vậy `==` trả `false`, còn `equals()` trả `true`. Hai biến `first`/`alias` trỏ tới một đối tượng nên identity hash code của chúng bằng nhau. `HashMap` gộp hai khóa tương đương theo giá trị thành một entry; `IdentityHashMap` giữ cả hai khóa vì khác tham chiếu. **Ví dụ cố ý không in và không giả định** `System.identityHashCode(first)` khác `System.identityHashCode(second)`; giả định đó sẽ sai khi có collision.

## 4. Vì sao hash không chứng minh được tính duy nhất?

Hàm băm ánh xạ rất nhiều đối tượng có thể tồn tại về một tập giá trị số hữu hạn. Việc một mã trông ngẫu nhiên hoặc ít khi trùng không biến nó thành mã duy nhất. `HashMap` và `IdentityHashMap` đều phải xử lý trường hợp các khóa có cùng hash: hash được dùng để tổ chức/tra cứu vị trí, còn phép so sánh khóa mới xác nhận khóa nào là khóa cần tìm. Đặc biệt, `IdentityHashMap` dùng so sánh **tham chiếu** dù hai khóa có thể cùng identity hash code.

Đừng viết điều kiện nhận dạng theo kiểu `System.identityHashCode(a) == System.identityHashCode(b)`; hãy dùng `a == b`. Cũng đừng lưu identity hash code làm khóa chính database, khóa cache dùng qua nhiều lần chạy, ID hiển thị cho người dùng, mã audit log cần truy vết lâu dài hay ID truyền giữa các dịch vụ.

### `ClassName@hex` trong log có phải ID duy nhất?

Không. Cách triển khai mặc định của `Object.toString()` ghép tên lớp, dấu `@` và biểu diễn hex của `hashCode()`. Phần hex ấy là **hash code**, không phải cam kết duy nhất; nếu lớp override `hashCode()` mà không override `toString()`, phần hex còn phản ánh phương thức `hashCode()` đã override. Một chuỗi như `Ticket@1a2b3c` không đủ để xác nhận đối tượng nào trên toàn hệ thống.

## 5. Khi nào dùng gì?

| Nhu cầu | Cách phù hợp |
| --- | --- |
| Kiểm tra hai biến có trỏ đúng cùng instance trong thời điểm hiện tại | `a == b` |
| Kiểm tra hai giá trị/nghiệp vụ tương đương | Cài đặt `equals()` và `hashCode()` nhất quán; dùng `Objects.equals(a, b)` khi cần an toàn với `null`. |
| Gom và tra cứu theo giá trị | `HashMap`, `HashSet` cùng hợp đồng `equals()`/`hashCode()`. |
| Theo dõi node trong đồ thị đối tượng, xử lý alias/cycle theo instance | `IdentityHashMap` hoặc `Collections.newSetFromMap(new IdentityHashMap<>())`. |
| Gắn nhãn băm hỗ trợ chẩn đoán một đối tượng đang sống | `System.identityHashCode(obj)`, thường kèm ngữ cảnh/lần chạy và kiểm tra `==` khi cần. |
| Nhận dạng thực thể qua restart, DB hoặc mạng | ID nghiệp vụ được lưu bền vững; ví dụ khóa chính DB có ràng buộc `UNIQUE`/`PRIMARY KEY`, hoặc UUID được cấp và quản lý. |

`UUID.randomUUID()` tạo UUID ngẫu nhiên với xác suất trùng rất thấp trong thực tế, **không phải bằng chứng toán học rằng không bao giờ trùng**. Nếu nghiệp vụ yêu cầu duy nhất nghiêm ngặt, hãy áp ràng buộc duy nhất ở nơi lưu trữ và xử lý khi có xung đột. Hai Java object khác nhau biểu diễn cùng bản ghi database có thể mang **cùng ID nghiệp vụ** mà vẫn `a != b` theo phép so sánh tham chiếu.

## 6. Sai lầm phổ biến và cách tránh

1. **Nhầm identity hash code với địa chỉ bộ nhớ.** Java không hứa mã băm là địa chỉ, cũng không hứa địa chỉ của đối tượng bất biến do GC.
2. **Dùng trùng hash để kết luận cùng object.** Collision hợp lệ; dùng `==` để kiểm tra identity.
3. **Dùng `hashCode()` để nhận dạng lâu dài.** Override, phiên chạy mới và collision đều khiến mã băm không phù hợp cho ID bền vững.
4. **So sánh đối tượng có cùng dữ liệu bằng `==`.** `==` có thể trả `false` dù `equals()` trả `true`; chọn phép so sánh theo mục tiêu.
5. **Giả định mọi object khác nhau có identity hash khác nhau.** Không có bảo đảm ấy; `IdentityHashMap` vẫn giữ được các khóa riêng nhờ kiểm tra tham chiếu.
6. **Lạm dụng `IdentityHashMap` cho dữ liệu nghiệp vụ.** Loại map này cố ý dùng identity thay cho value equality, vì thế kết quả có thể trái trực giác nếu gọi với các khóa bằng nhau theo `equals()`.

## 7. Tự kiểm tra

- Hai biến cùng tham chiếu mà identity hash code khác nhau trong một lần chạy được không? **Không**.
- Hai instance khác nhau mà identity hash code trùng nhau được không? **Có**, vì mã băm có thể va chạm.
- Hai đối tượng `equals()` bằng nhau mà identity hash code khác nhau được không? **Có**.
- Có nên dùng `System.identityHashCode()` làm mã đơn hàng duy nhất không? **Không**; dùng ID được cấp phát và xác thực tính duy nhất bởi hệ thống lưu trữ.

**Ghi nhớ:** *Identity* được xác nhận bằng cùng tham chiếu (`==`); *identity hash code* là số băm hỗ trợ cơ chế theo danh tính; *unique identifier* là định danh do thiết kế hệ thống quy định và duy trì.

## Tài liệu tham khảo

- [Java SE 17 — `System.identityHashCode(Object)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#identityHashCode(java.lang.Object))
- [Java SE 17 — hợp đồng `Object.hashCode()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#hashCode())
- [Java SE 17 — `IdentityHashMap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IdentityHashMap.html)
