# Giới hạn gán trường thành phần trong compact constructor của Java record

## 1. Quy tắc quan trọng nhất

Với một `record`, các tên trong **record header** là *record components*. Mỗi component có một trường instance tương ứng, do Java khai báo ngầm định với các thuộc tính **`private final`**. Khi viết **compact canonical constructor** (thường gọi ngắn là *compact constructor*), lập trình viên **không được tự gán** vào các trường thành phần ấy trong thân constructor.

Ví dụ:

```java
record Person(String name, int age) {
    Person {
        name = name.trim(); // ĐÚNG: gán lại tham số ngầm định "name"
        if (age < 0) {
            throw new IllegalArgumentException("age must be >= 0");
        }
        // this.name = name; // SAI: không được tự gán component field
        // this.age = age;   // SAI: Java tự khởi tạo sau thân constructor
    }
}
```

**Phân biệt hai đối tượng được gán:**

- `name = name.trim();`: vế trái `name` là **tham số ngầm định của constructor**, có thể thay đổi để chuẩn hóa đầu vào.
- `this.name = name;`: vế trái `this.name` là **component field `private final`** của object; gán như vậy trong compact constructor là lỗi biên dịch.
- Nếu thân compact constructor hoàn tất **bình thường**, Java tự gán các tham số cuối cùng cho các component fields theo thứ tự khai báo trên header. Vì thế **không cần** viết câu lệnh khởi tạo trường.

Record đã trở thành tính năng chính thức từ **Java 16** (JEP 395), và các quy tắc này vẫn có trong Java hiện hành. Những ví dụ trong bài dùng Java **17+**, không dựa vào record preview trước đây.

## 2. Constructor nào đang được nói đến?

```java
record Product(String code, int quantity) {
    Product {
        // Compact constructor: KHÔNG lặp lại danh sách tham số.
    }
}
```

`Product { ... }` là một **compact canonical constructor**. Chữ ký và danh sách tham số của nó do Java suy ra từ `(String code, int quantity)` trong header. Điều này khác với **normal canonical constructor**:

```java
record Product(String code, int quantity) {
    Product(String code, int quantity) {
        // Normal canonical constructor: khai báo đầy đủ tham số.
        this.code = code;
        this.quantity = quantity;
    }
}
```

Hai ví dụ trên là **hai phiên bản thay thế nhau** của cùng record; **không đặt cả hai constructor trong cùng một record**, vì chúng cùng đại diện cho canonical constructor.

| Đặc điểm | Compact canonical constructor | Normal canonical constructor |
| --- | --- | --- |
| Cú pháp | `Product { ... }` | `Product(String code, int quantity) { ... }` |
| Tham số component | Ngầm định từ header | Viết tường minh |
| Được gán lại tham số để chuẩn hóa? | Có: `code = code.trim()` | Có nếu tham số không khai báo `final` |
| Được viết `this.code = code;`? | **Không** | **Có**, và cần khởi tạo đủ các component fields theo quy tắc *definite assignment* |
| Ai khởi tạo component fields? | Java tự gán khi thân compact constructor hoàn tất bình thường | Constructor tường minh phải chịu trách nhiệm khởi tạo |
| Dùng phù hợp | Validate, chuẩn hóa, sao chép phòng vệ đầu vào | Cần điều khiển khởi tạo trường theo dạng constructor đầy đủ |

**Đừng nhầm:** Quy tắc “cấm `this.code = ...`” áp dụng cho **thân compact constructor**. Gán component field trong **normal canonical constructor** hợp lệ khi đáp ứng các quy tắc dành cho trường `final`; đó là hai kiểu khai báo khác nhau.

## 3. Cơ chế Java gán trường sau compact constructor

Xét:

```java
record Interval(int start, int end) {
    Interval {
        if (start > end) {
            int temp = start;
            start = end;
            end = temp;
        }
    }
}
```

Với `new Interval(9, 3)`, luồng khái niệm là:

1. Tham số ngầm định ban đầu: `start = 9`, `end = 3`.
2. Kiểm tra `start > end` đúng, nên hai **tham số** được hoán đổi: `start = 3`, `end = 9`.
3. Thân compact constructor kết thúc bình thường.
4. **Java ngầm gán** `this.start` bằng tham số `start` (3) và `this.end` bằng tham số `end` (9).
5. Record được khởi tạo hoàn chỉnh. `new Interval(9, 3)` cho biểu diễn `Interval[start=3, end=9]`.

Để hiểu hiệu ứng, có thể hình dung thao tác tự động sau ở **mức ngữ nghĩa** (không viết vào compact constructor):

```java
// MÔ PHỎNG Ý NGHĨA cuối compact constructor, KHÔNG phải mã được phép chép vào:
this.start = start;
this.end = end;
```

Theo đặc tả, Java khởi tạo các component fields theo **thứ tự các component khai báo trong header**. Nếu thân constructor ném ngoại lệ, constructor **không hoàn tất bình thường**, nên đối tượng không được trả về như một instance đã khởi tạo thành công.

### Vì sao `start` và `this.start` khác nhau?

Trong thân compact constructor, tên đơn giản `start` biểu thị **tham số ngầm định `start`**, không phải trường của instance. Điều này cho phép kiểm tra và sửa giá trị đầu vào:

```java
record NonNegative(int value) {
    NonNegative {
        value = Math.max(0, value); // HỢP LỆ: sửa tham số
    }
}
```

Trường tương ứng vẫn là `private final int value`. Java không có cơ chế setter cho component field sau khi constructor kết thúc.

## 4. Điều được làm: kiểm tra và chuẩn hóa tham số

Compact constructor được thiết kế để **validate** dữ liệu và/hoặc **normalize** các tham số trước khi Java tự lưu chúng vào trường.

### 4.1. Chặn dữ liệu sai bằng ngoại lệ

```java
record Age(int value) {
    Age {
        if (value < 0 || value > 150) {
            throw new IllegalArgumentException("Invalid age: " + value);
        }
    }
}
```

`new Age(25)` hợp lệ; `new Age(-1)` ném `IllegalArgumentException`. **`throw` là hợp lệ** trong compact constructor; nó dừng việc tạo đối tượng khi dữ liệu đầu vào không hợp lệ.

### 4.2. Chuẩn hóa chuỗi trước khi lưu

```java
record Username(String value) {
    Username {
        value = java.util.Objects.requireNonNull(value, "value").trim();
        if (value.isEmpty()) {
            throw new IllegalArgumentException("Username is empty");
        }
        value = value.toLowerCase(java.util.Locale.ROOT);
    }
}
```

`new Username("  ALICE ")` dẫn đến `value()` trả `"alice"`. Các phép gán đều tác động vào **tham số `value`**, và Java lưu phiên bản cuối khi khởi tạo component field.

Trong xử lý chuỗi dùng để lưu trữ/đối chiếu không phụ thuộc ngôn ngữ tự nhiên, `Locale.ROOT` tránh sự phụ thuộc ngoài ý muốn vào locale mặc định của máy. Việc có nên lowercase dữ liệu là quyết định nghiệp vụ; không áp dụng tự động với thông tin phân biệt chữ hoa/chữ thường.

### 4.3. Sao chép đầu vào tham chiếu khi cần

```java
record Tags(java.util.List<String> values) {
    Tags {
        values = java.util.List.copyOf(values); // Gán lại THAM SỐ
    }
}
```

`List.copyOf` tạo ra danh sách không sửa được và tránh giữ tham chiếu đến một danh sách nguồn có thể bị sửa. Record chỉ bảo đảm **bất biến nông** cho trường `private final`: nếu một component chứa `List`, mảng, hay đối tượng mutable, bản thân `final` không tự đóng băng dữ liệu phía trong. Với danh sách các phần tử mutable, còn cần xem xét sao chép/thiết kế ở cấp phần tử.

Ví dụ trên vẫn tuân thủ nguyên tắc: thay tham số `values` bằng tham chiếu đến danh sách đã được phòng vệ; **không** dùng `this.values = ...` trong compact constructor.

## 5. Điều bị cấm: tự gán component fields

### 5.1. Gán trực tiếp `this.field = ...` là lỗi

Tệp sau **cố ý không biên dịch**:

```java
// BadField.java — cố ý sai để quan sát compiler
record BadField(int value) {
    BadField {
        this.value = value;
    }
}
```

Lệnh:

```bash
javac --release 17 BadField.java
```

Kết quả là **lỗi biên dịch**, chẳng hạn `cannot assign a value to final variable value`. Java không “bỏ qua” dòng gán này rồi tự khởi tạo lần nữa: việc gán component field trong thân compact constructor bị cấm.

Sửa:

```java
record FixedField(int value) {
    FixedField {
        if (value < 0) {
            throw new IllegalArgumentException("negative value");
        }
        // Không cần this.value = value.
    }
}
```

### 5.2. Gán kết hợp hoặc tăng/giảm trường cũng sai

Các biểu thức sau đều cố thay đổi **component field** và **không hợp lệ** trong thân compact constructor:

```java
// Những dòng cố ý sai nếu đặt trong record Counter(int count) { Counter { ... } }
this.count += 1; // SAI: compound assignment vào component field
this.count++;    // SAI: tăng component field
++this.count;    // SAI: tăng component field
```

Ngược lại, `count += 1;` hoặc `count++;` (không có `this.`) thay đổi **tham số ngầm định** và hợp lệ khi kiểu/phép toán cho phép. Cần phân biệt rõ biến bị gán, không chỉ nhìn thấy toán tử `=`.

### 5.3. Đọc trường chưa được khởi tạo là vấn đề khác

Trong thân compact constructor, việc cố đọc trực tiếp `this.value` trước điểm tự khởi tạo có thể bị chặn bởi kiểm tra *definite assignment*:

```java
// BadRead.java — cố ý sai
record BadRead(int value) {
    BadRead {
        System.out.println(this.value); // LỖI: value có thể chưa được khởi tạo
    }
}
```

Với `javac --release 17`, ví dụ trên báo `variable value might not have been initialized`. Nếu cần kiểm tra hay in giá trị đầu vào bên trong compact constructor, hãy dùng **tham số**:

```java
record DebugValue(int value) {
    DebugValue {
        System.out.println(value); // Đúng: đọc tham số ngầm định
    }
}
```

Không dựa vào accessor `value()` trong giai đoạn khởi tạo để lấy một trạng thái component field chưa được hoàn tất. Chuẩn hóa mọi dữ liệu thông qua các tham số trước khi kết thúc compact constructor.

## 6. Giới hạn điều khiển luồng cũng ảnh hưởng đến phép gán

### 6.1. Không viết `return` trong thân compact constructor

```java
// BadReturn.java — cố ý không biên dịch
record BadReturn(int value) {
    BadReturn {
        if (value == 0) {
            return; // LỖI: compact constructor không được chứa return
        }
    }
}
```

Với `javac --release 17`, trình biên dịch báo lỗi kiểu `compact constructor must not have return statements`. Dù `return;` không mang giá trị, nó vẫn không được phép trong compact constructor.

Nếu muốn bác bỏ giá trị không hợp lệ, dùng `throw new IllegalArgumentException(...)`; nếu muốn chấp nhận, để luồng chạy đến cuối thân constructor, Java sẽ tự gán các trường. `return` không phải cách bỏ qua việc khởi tạo một vài component.

### 6.2. Không gọi constructor khác bằng `this(...)` hoặc `super(...)` trong thân compact constructor

Một compact constructor không được chứa **explicit constructor invocation**. Vì nó chính là canonical constructor, Java đã xác định trách nhiệm khởi tạo tất cả component fields sau khi thân hoàn tất bình thường.

Nếu muốn có **constructor phụ** nhận danh sách tham số khác, viết constructor phụ riêng và ủy quyền về canonical constructor:

```java
record Product(String code, int quantity) {
    Product {
        code = code.trim();
        if (quantity < 0) throw new IllegalArgumentException("negative quantity");
    }

    Product(String code) {
        this(code, 1); // HỢP LỆ trong constructor phụ, không đặt trong Product { ... }
    }
}
```

Không tạo thêm một compact constructor thứ hai hoặc đồng thời khai báo compact constructor và normal canonical constructor với cùng chữ ký trong một record.

### 6.3. Tất cả component fields được khởi tạo như một bộ

Dù compact constructor chỉ kiểm tra một component, Java vẫn tự gán **tất cả** component fields sau thân constructor. Không phải viết lệnh gán cho từng trường và cũng không thể lựa chọn “chỉ khởi tạo `name`, để `age` chưa khởi tạo” trên một đối tượng tạo thành công.

```java
record Person(String name, int age) {
    Person {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name required");
        }
        // age không bị thay đổi, nhưng Java vẫn tự khởi tạo age từ tham số.
    }
}
```

## 7. Ví dụ độc lập chạy được với Java 17+

Lưu thành tệp **`CompactConstructorDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public class CompactConstructorDemo {
    record Interval(int start, int end) {
        Interval {
            if (start > end) {
                int temp = start;
                start = end;
                end = temp;
            }
        }
    }

    record Product(String code, int quantity) {
        Product {
            code = Objects.requireNonNull(code, "code")
                    .trim().toUpperCase(Locale.ROOT);
            if (code.isBlank()) {
                throw new IllegalArgumentException("empty code");
            }
            if (quantity < 0) {
                throw new IllegalArgumentException("negative quantity");
            }
        }

        Product(String code) {
            this(code, 1);
        }
    }

    record Tags(List<String> values) {
        Tags {
            values = List.copyOf(values);
        }
    }

    record Explicit(int value) {
        Explicit(int value) {
            if (value < 0) {
                throw new IllegalArgumentException("negative value");
            }
            this.value = value;
        }
    }

    public static void main(String[] args) {
        System.out.println(new Interval(9, 3));
        System.out.println(new Product("  item-7 ", 2));
        System.out.println(new Product(" box ").code());

        ArrayList<String> input = new ArrayList<>(List.of("java"));
        Tags tags = new Tags(input);
        input.add("changed");
        System.out.println(tags.values());

        System.out.println(new Explicit(4).value());

        try {
            new Product("  ", 3);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected: " + ex.getMessage());
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 CompactConstructorDemo.java
java CompactConstructorDemo
```

Kết quả chuẩn:

```text
Interval[start=3, end=9]
Product[code=ITEM-7, quantity=2]
BOX
[java]
4
Rejected: empty code
```

**Giải thích theo từng dòng:**

1. `Interval[start=3, end=9]`: hai **tham số** `start`/`end` được đổi chỗ; Java tự khởi tạo hai component fields bằng các giá trị cuối.
2. `Product[code=ITEM-7, quantity=2]`: tham số `code` được trim rồi chuyển uppercase; `quantity` giữ nguyên.
3. `BOX`: constructor phụ `Product(String)` gọi `this(code, 1)` để về compact canonical constructor; accessor `code()` thấy dữ liệu đã được chuẩn hóa.
4. `[java]`: tham số `values` được thay bằng `List.copyOf(values)` trước khi Java khởi tạo field. Sửa danh sách gốc sau đó không làm đổi danh sách đã lưu.
5. `4`: normal canonical constructor `Explicit(int value)` dùng `this.value = value;` **hợp lệ**. Điều này đối chiếu trực tiếp với lệnh gán bị cấm ở compact constructor.
6. `Rejected: empty code`: compact constructor kiểm tra tên rỗng và ném ngoại lệ; không có `Product` hợp lệ nào được trả về.

Ví dụ được thiết kế với tính năng record đã chính thức, không cần `--enable-preview`.

## 8. Bảng xử lý tình huống thực tế

| Việc muốn làm trong compact constructor | Cách đúng | Cách sai/nhầm |
| --- | --- | --- |
| Chuẩn hóa tên | `name = name.trim();` | `this.name = name.trim();` |
| Ép giá trị không âm | `value = Math.max(value, 0);` | `this.value = Math.max(this.value, 0);` |
| Đổi chỗ hai mốc | Đổi `start`, `end` (tham số) | Đổi `this.start`, `this.end` |
| Kiểm tra điều kiện | `if (x < 0) throw ...;` | Dùng `return;` để kết thúc sớm |
| Copy danh sách | `items = List.copyOf(items);` | `this.items = List.copyOf(items);` |
| Gán toàn bộ trường | **Để Java tự thực hiện** | Viết lệnh `this.field = ...` |
| Muốn tự điều khiển gán field | Chọn **normal canonical constructor** | Vẫn dùng compact constructor rồi tự gán field |
| Muốn thêm constructor nhận ít tham số | Viết constructor phụ gọi `this(...)` tới canonical constructor | Gọi `this(...)` trong thân compact constructor |

## 9. Bài tập tự kiểm tra

### Câu 1. Đoạn nào hợp lệ?

```java
record Total(int amount) {
    Total {
        amount += 10;       // (A)
        // this.amount += 10; // (B)
    }
}
```

**Đáp án:** (A) hợp lệ vì sửa tham số. Nếu bỏ chú thích (B), biên dịch lỗi vì cố sửa component field trong compact constructor.

### Câu 2. Khi nào các trường được khởi tạo?

```java
record Label(String value) {
    Label {
        value = value.strip();
    }
}
```

**Đáp án:** Sau khi thân compact constructor hoàn tất bình thường, Java tự khởi tạo trường `private final String value` từ tham số `value` đã được `strip()`. Accessor `value()` sau đó trả chuỗi đã chuẩn hóa.

### Câu 3. Có thể vừa compact vừa normal canonical constructor?

**Đáp án:** Không, vì cả hai cùng đại diện cho canonical constructor và có chữ ký tương ứng nhau. Chọn **một** dạng; vẫn có thể có constructor phụ với danh sách tham số khác và ủy quyền tới canonical constructor.

### Câu 4. `throw` có giống `return` không?

**Đáp án:** Không. `throw` hợp lệ khi dữ liệu sai và làm quá trình tạo object thất bại bằng ngoại lệ. `return` bị cấm trong thân compact constructor, kể cả `return;`.

### Câu 5. Vì sao `final` không làm `List<String>` bất biến hoàn toàn?

**Đáp án:** `final` ngăn thay đổi **tham chiếu component field**, không cấm sửa đối tượng được tham chiếu. Gán `items = List.copyOf(items);` vào tham số trước khi constructor kết thúc giúp bảo vệ cấu trúc danh sách, nhưng phần tử mutable bên trong vẫn cần xem xét.

## 10. Checklist dùng trong mã thật

- [ ] Trong `RecordName { ... }` chỉ thao tác với **tham số ngầm định** khi validate/normalize, không tự gán `this.component`.
- [ ] Không để `return`, `this(...)` hoặc `super(...)` trong thân compact constructor.
- [ ] Khi dữ liệu không hợp lệ, ném ngoại lệ; khi hợp lệ, để thân constructor kết thúc bình thường.
- [ ] Với component tham chiếu, cân nhắc `Objects.requireNonNull`, `List.copyOf` hoặc defensive copy phù hợp **trước** bước Java tự khởi tạo field.
- [ ] Nếu thực sự cần tự viết `this.component = ...`, cân nhắc normal canonical constructor và kiểm tra khởi tạo đầy đủ trường `final`.
- [ ] Mỗi record có tối đa một canonical constructor được áp dụng; constructor phụ cần ủy quyền phù hợp.
- [ ] Dùng JDK 17+ hoặc `javac --release 17` để thực hành với record đã chính thức; không cần tính năng preview cũ.

## Tài liệu chuẩn còn áp dụng

- [Java Language Specification, Java SE 26 — `8.10.4.2 Compact Canonical Constructors](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-8.html#jls-8.10.4.2): nguyên tắc cấm gán component fields trong thân compact constructor, tham số ngầm định, tự khởi tạo cuối thân, cấm `return` và lời gọi constructor tường minh.
- [Java Language Specification, Java SE 26 — `8.10.3 Record Members](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-8.html#jls-8.10.3): mỗi component tương ứng với trường `private final` và accessor.
- [Java SE 27 — Java Language Specification](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/index.html): bộ đặc tả Java hiện hành, bao gồm quy tắc record constructors.
- [Oracle — Record Classes (Java 25)](https://docs.oracle.com/en/java/javase/25/language/records.html): ví dụ compact constructor, canonical constructor và constructor phụ.
