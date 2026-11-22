# Giới hạn chia sẻ trạng thái và hợp đồng của default method

Default method chia sẻ **cách thực hiện một hành vi**, không tạo trạng thái riêng cho từng đối tượng và không tự bảo đảm mọi lớp triển khai tuân thủ cùng một quy tắc nghiệp vụ. Trạng thái, bất biến và đồng bộ vẫn phải thuộc về nơi sở hữu dữ liệu.

## 1. Hành vi dùng chung không phải trạng thái dùng chung

```java
interface Greeter {
    String name();

    default String greet() {
        return "Xin chào, " + name();
    }
}
```

`greet()` chỉ dựa vào hợp đồng `name()`. Tên có thể đến từ trường của class, cơ sở dữ liệu, một đối tượng thành phần hoặc giá trị được tính toán. Default method không cần biết chi tiết đó; nó cũng không thể truy cập trực tiếp trường riêng chỉ tồn tại trong một class.

Interface không có constructor và không thể khai báo instance field. Mọi field khai báo trong interface đều ngầm định `public static final`. Vì thế:

```java
interface Settings {
    int MAX_RETRIES = 3;
}
```

`MAX_RETRIES` là hằng cấp interface, không phải biến riêng của mỗi instance. Từ khóa `final` ngăn gán lại biến tham chiếu, nhưng không làm đối tượng mutable mà nó trỏ tới trở thành bất biến.

## 2. Cẩn thận với đối tượng mutable trong field interface

```java
import java.util.ArrayList;
import java.util.List;

interface SharedRecords {
    List<String> RECORDS = new ArrayList<>();

    default void record(String value) {
        RECORDS.add(value);
    }
}
```

Đoạn mã này hợp lệ nhưng danh sách `RECORDS` là một tham chiếu `public static final` dùng chung, không phải danh sách riêng của từng đối tượng. Mọi nơi có quyền truy cập có thể thay đổi nội dung của nó; `ArrayList` cũng không tự bảo đảm an toàn luồng. Đặt cache hoặc collection mutable trong interface thường vô tình tạo trạng thái dùng chung khó kiểm soát.

Nếu cần trạng thái theo instance, hãy đặt nó trong lớp triển khai. Nếu cần trạng thái dùng chung, đặt nó trong một thành phần có chủ sở hữu, vòng đời và chính sách đồng bộ rõ ràng.

## 3. Ví dụ: chia sẻ thuật toán nhưng giữ trạng thái riêng

```java
public class DefaultStateDemo {
    interface Counter {
        int value();
        void add(int delta);

        default void increment() {
            add(1);
        }

        default boolean isZero() {
            return value() == 0;
        }
    }

    static final class MemoryCounter implements Counter {
        private int current;

        @Override
        public int value() {
            return current;
        }

        @Override
        public void add(int delta) {
            if (delta < 0) {
                throw new IllegalArgumentException("delta must be non-negative");
            }
            current = Math.addExact(current, delta);
        }
    }

    public static void main(String[] args) {
        Counter first = new MemoryCounter();
        Counter second = new MemoryCounter();
        first.increment();
        first.increment();

        System.out.println(first.value());
        System.out.println(second.value());
        System.out.println(first.isZero());
        System.out.println(second.isZero());
    }
}
```

Kết quả:

```text
2
0
false
true
```

Cả hai đối tượng dùng chung implementation của `increment()` và `isZero()`, nhưng mỗi `MemoryCounter` có trường `current` riêng. Ví dụ chạy tuần tự; nó không làm `MemoryCounter` an toàn khi nhiều luồng cập nhật cùng lúc.

## 4. Hợp đồng phải nêu rõ tiền điều kiện và tác động

Một default method có thể ghép nhiều thao tác, nhưng chữ ký Java không tự định nghĩa đầy đủ ý nghĩa của chúng. Với mỗi phương thức hợp đồng, hãy làm rõ:

| Khía cạnh | Điều cần quy định |
| --- | --- |
| Tiền điều kiện | Đầu vào null, âm, rỗng hoặc ngoài miền xử lý được xử lý thế nào? |
| Hậu điều kiện | Sau khi thành công, kết quả và trạng thái thay đổi ra sao? |
| Ngoại lệ | Lỗi được trả qua giá trị hay exception nào? |
| Side effect | Phương thức có sửa dữ liệu, I/O hoặc gọi dịch vụ khác không? |
| Đồng thời | Thao tác có cần atomic hoặc thread-safe không? |
| Override | Implementation riêng có phải giữ cùng cam kết ngữ nghĩa không? |

Ví dụ thiết kế có vấn đề:

```java
interface Inventory {
    int available();
    void reserve(int units);

    default boolean tryReserve(int units) {
        if (available() >= units) {
            reserve(units);
            return true;
        }
        return false;
    }
}
```

Hai lời gọi `available()` và `reserve()` độc lập. Một luồng khác có thể thay đổi tồn kho giữa lúc kiểm tra và cập nhật; default method không biến chuỗi thao tác thành giao dịch atomic. Ví dụ còn thiếu quy tắc cho `units <= 0` và cách báo thất bại.

Nếu kiểm tra và cập nhật phải là một thao tác nguyên tử, hãy để lớp sở hữu trạng thái triển khai một phương thức hợp đồng duy nhất như `tryReserve(int units)`. Default method có thể tổng hợp các thao tác đọc an toàn, nhưng không nên giả định nó có thể cưỡng chế bất biến của trạng thái mà interface không sở hữu.

## 5. Chọn cơ chế phù hợp

| Nhu cầu | Lựa chọn thường phù hợp |
| --- | --- |
| Hành vi nhỏ được tính từ các phương thức hợp đồng rõ ràng | Default method |
| Mỗi implementation phải tự quyết định một hành vi quan trọng | Phương thức abstract |
| Trạng thái instance, constructor và logic cốt lõi dùng chung | Abstract class nếu quan hệ kế thừa phù hợp |
| Cache, giao dịch, I/O hoặc dependency có vòng đời | Service hoặc đối tượng thành phần |
| Helper chỉ phục vụ các phương thức trong interface | Private method của interface từ Java 9 |

Một default method cũng có thể bị override; nó không phải cơ chế bảo đảm thuật toán sẽ luôn chạy. Khi phát hành API, hãy kiểm tra xung đột phương thức và tương thích hành vi với các implementer hiện có. Mã biên dịch được chưa đủ chứng minh rằng mọi implementation giữ đúng tiền điều kiện, hậu điều kiện hoặc cam kết đồng thời.

## Tự kiểm tra

1. Vì sao field khai báo trong interface không phải trạng thái riêng của từng đối tượng?
2. Tại sao `static final` không làm một `ArrayList` trở thành bất biến?
3. Vì sao `available()` rồi `reserve()` trong default method không tự tạo tính atomic?
4. Khi nào nên đưa một thao tác vào phương thức abstract do class sở hữu thay vì tổng hợp trong default method?

**Ghi nhớ:** default method chia sẻ logic. Lớp triển khai hoặc thành phần chuyên trách sở hữu dữ liệu, bất biến và cơ chế đồng bộ. Hợp đồng phải mô tả rõ cách xử lý đầu vào, lỗi, side effect và tính đồng thời.