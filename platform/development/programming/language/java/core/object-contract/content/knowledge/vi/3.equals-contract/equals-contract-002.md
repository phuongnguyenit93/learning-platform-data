# Tính phản xạ của `equals(Object)` trong Java

## 1. Tính phản xạ là gì?

Trong hợp đồng của `Object.equals(Object)`, **tính phản xạ (reflexivity)** yêu cầu: với mọi tham chiếu `x` khác `null`, lời gọi `x.equals(x)` phải trả về `true`.

```text
Với mọi x != null: x.equals(x) == true
```

Ở đây, hai vế `x` đều chỉ **cùng một đối tượng đang tồn tại**. Đây là quy tắc tối thiểu mà mọi cách cài đặt lại `equals` phải tôn trọng: một đối tượng không được tự tuyên bố rằng nó khác chính nó.

Điểm cần phân biệt:

- `x == x` luôn là `true` đối với một tham chiếu `x`: toán tử `==` so sánh danh tính tham chiếu.
- `x.equals(x)` **phải** là `true` theo hợp đồng, nhưng phương thức `equals` có thể bị người lập trình override sai.
- Hai đối tượng **khác tham chiếu** vẫn có thể bằng nhau về mặt logic nếu lớp định nghĩa `equals` theo các thuộc tính có ý nghĩa. Đây là câu hỏi khác với việc một đối tượng bằng chính nó.
- `null` không phải một đối tượng để gọi phương thức: `null.equals(null)` ném `NullPointerException`. Hợp đồng phản xạ chỉ phát biểu cho tham chiếu khác `null`.

## 2. Vì sao quy tắc này tồn tại?

`equals` biểu diễn một quan hệ bình đẳng theo nghĩa logic do lớp định nghĩa. Nếu quan hệ đó cho phép `x.equals(x) == false`, ngay cả trường hợp so sánh dễ nhất cũng không còn đáng tin cậy. Các phép kiểm tra, thuật toán và API dùng bình đẳng đối tượng thường xây dựng trên giả định rằng một cách cài đặt `equals` tuân thủ hợp đồng chuẩn.

Cài đặt `Object.equals` mặc định dùng bình đẳng danh tính: chỉ cùng một đối tượng mới bằng nhau. Vì vậy nó đã có tính phản xạ. Khi override để so sánh theo giá trị, lập trình viên phải **giữ lại** đặc tính ấy.

Tính phản xạ không có nghĩa là mọi đối tượng cùng lớp đều bằng nhau. Nó cũng không đòi hỏi tất cả trường dữ liệu phải khác `null`, bất biến hay có một giá trị nhất định; đối tượng nào cũng phải bằng chính nó.

## 3. Cài đặt `equals` đúng và kiểm chứng bằng Java 17

Ví dụ dưới đây đặt nhánh `this == other` lên đầu phương thức. Đây là cách viết rõ ràng và thường hiệu quả để bảo đảm trường hợp hai tham chiếu trỏ tới cùng một đối tượng trả về `true` ngay lập tức.

Tạo tệp **`ReflexivityDemo.java`**:

```java
import java.util.Objects;

public class ReflexivityDemo {
    static final class Person {
        private final String name;
        private final int age;

        Person(String name, int age) {
            this.name = name;
            this.age = age;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true; // Cùng một đối tượng: luôn bằng chính nó.
            }
            if (!(other instanceof Person person)) {
                return false; // Bao gồm cả trường hợp other == null.
            }
            return age == person.age
                    && Objects.equals(name, person.name);
        }

        @Override
        public int hashCode() {
            return Objects.hash(name, age);
        }
    }

    static final class BrokenPerson {
        private final String name;

        BrokenPerson(String name) {
            this.name = name;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return false; // SAI: vi phạm tính phản xạ.
            }
            return other instanceof BrokenPerson person
                    && Objects.equals(name, person.name);
        }

        @Override
        public int hashCode() {
            return Objects.hashCode(name);
        }
    }

    public static void main(String[] args) {
        Person p = new Person(null, 20);
        Person q = new Person(null, 20);

        System.out.println("p == p: " + (p == p));
        System.out.println("p.equals(p): " + p.equals(p));
        System.out.println("p.equals(q): " + p.equals(q));
        System.out.println("p.equals(null): " + p.equals(null));

        BrokenPerson broken = new BrokenPerson("An");
        System.out.println("broken.equals(broken): "
                + broken.equals(broken));
        System.out.println("Objects.equals(broken, broken): "
                + Objects.equals(broken, broken));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 ReflexivityDemo.java
java ReflexivityDemo
```

Kết quả chính xác:

```text
p == p: true
p.equals(p): true
p.equals(q): true
p.equals(null): false
broken.equals(broken): false
Objects.equals(broken, broken): true
```

Giải thích từng trường hợp:

1. `p == p` là `true` vì hai vế là cùng tham chiếu.
2. `p.equals(p)` là `true` vì `this == other` trả về ngay, đáp ứng tính phản xạ.
3. `p.equals(q)` cũng là `true`, **nhưng vì hai đối tượng khác nhau có cùng `name` và `age`**. Điều này thuộc cách lớp định nghĩa bình đẳng theo giá trị; không phải phép kiểm tra tính phản xạ. Ví dụ cố ý dùng `name == null` để cho thấy trường `null` không làm mất tính phản xạ.
4. `p.equals(null)` là `false` theo kiểm tra `instanceof`. Điều này khác với việc gọi phương thức trên tham chiếu `null`.
5. `broken.equals(broken)` là `false` do nhánh sai trong `BrokenPerson.equals`, chứng minh rằng một override thực sự có thể phá vỡ hợp đồng.
6. `Objects.equals(broken, broken)` lại là `true`, vì tiện ích `Objects.equals(a, b)` kiểm tra `a == b` trước khi gọi `a.equals(b)`. **Không dùng `Objects.equals(x, x)` làm phép thử duy nhất để phát hiện `equals` thiếu tính phản xạ**: phép thử đó có thể che lỗi.

Hai lớp trong ví dụ đều override `hashCode` theo các trường so sánh để duy trì quy tắc liên quan đến các đối tượng bằng nhau. Tuy vậy, việc có `hashCode` hợp lý **không thể cứu** một cài đặt `equals` đã vi phạm tính phản xạ.

## 4. Có bắt buộc viết `if (this == other) return true;` không?

**Không bắt buộc về cú pháp.** Bắt buộc là **kết quả hành vi**: `x.equals(x)` phải là `true`.

Ví dụ, nếu phần còn lại của `equals` so sánh đầy đủ và đúng các trường với chính chúng, phương thức vẫn có thể phản xạ mà không cần nhánh tối ưu đầu tiên. Tuy nhiên, nhánh `this == other` có ba lợi ích rõ ràng:

- Làm hợp đồng dễ nhận ra khi đọc code.
- Tránh phải đi qua các phép so sánh thuộc tính khi hai tham chiếu đã là một.
- Giảm nguy cơ trường hợp tự so sánh đi vào những nhánh xử lý sai.

Nhánh này không thay thế việc kiểm tra kiểu, so sánh đúng các thuộc tính khi hai đối tượng khác nhau, hoặc tuân thủ các điều khoản khác của hợp đồng `equals`. Một phương thức có thể phản xạ nhưng vẫn sai ở những khía cạnh khác.

## 5. Lỗi thường gặp và cách kiểm tra

**Lỗi 1 — trả về `false` khi hai tham chiếu giống nhau.** Ví dụ `BrokenPerson` ở trên đảo ngược điều kiện cần có. Cách sửa trực tiếp là trả `true` khi `this == other`.

**Lỗi 2 — dùng `==` thay cho `equals` rồi kết luận toàn bộ phương thức đúng.** `x == x` chỉ kiểm tra danh tính tham chiếu. Nó không kiểm tra implementation của `equals`, nên một lớp có `equals` sai vẫn vượt qua phép thử `x == x`.

**Lỗi 3 — kiểm tra gián tiếp bằng một tiện ích tối ưu hóa.** `Objects.equals(x, x)` trả `true` ngay khi hai tham chiếu giống nhau. Hãy gọi thẳng `x.equals(x)` để kiểm tra hợp đồng của lớp.

**Lỗi 4 — nhầm `null` với một đối tượng đặc biệt.** Không thể gọi `null.equals(null)`; đừng đưa `null` vào miền giá trị của phát biểu phản xạ. Nếu cần so sánh hai tham chiếu có thể `null`, `Objects.equals(a, b)` là API tiện lợi, nhưng đó là mục đích khác.

**Lỗi 5 — cho điều kiện tự so sánh phụ thuộc dữ liệu.** Chẳng hạn, chỉ trả về `true` khi trường `name` khác `null` là sai: đối tượng với `name == null` vẫn phải bằng chính nó.

Có thể tạo một phép kiểm tra hồi quy ngắn, không cần thư viện kiểm thử:

```java
static void checkReflexive(Object value) {
    Objects.requireNonNull(value, "value");
    if (!value.equals(value)) {
        throw new AssertionError("equals vi pham tinh phan xa");
    }
}
```

Đây là **đoạn phương thức minh họa**, đặt bên trong một lớp Java thích hợp rồi gọi với nhiều đối tượng đại diện (các trường hợp bình thường, trường có `null`, giá trị biên). Nó kiểm tra trực tiếp đúng điều khoản phản xạ. Nếu đang dùng JUnit, ý tưởng tương đương là `assertTrue(value.equals(value))` đối với từng giá trị khác `null`.

## 6. Ghi nhớ

- Phát biểu chuẩn: **với mọi tham chiếu `x` khác `null`, `x.equals(x)` phải trả về `true`**.
- Đây là yêu cầu đối với implementation `equals` của lớp, không chỉ là tính chất của toán tử `==`.
- `if (this == other) return true;` là cách thực hiện thông dụng, rõ ràng, nhưng không phải cú pháp bắt buộc.
- Kiểm tra trực tiếp `x.equals(x)`; `Objects.equals(x, x)` có thể che lỗi vì tối ưu hóa so sánh tham chiếu.
- Nếu một đối tượng có thể `equals` với chính nó trả về `false`, implementation đã vi phạm hợp đồng và cần được sửa.
