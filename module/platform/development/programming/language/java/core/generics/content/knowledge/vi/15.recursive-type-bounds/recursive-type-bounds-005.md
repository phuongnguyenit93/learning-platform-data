# Mẫu tự tham chiếu trong builder có kế thừa — Java Generics

## 1. Vấn đề: kế thừa làm mất kiểu khi gọi nối chuỗi

**Builder** là đối tượng gom các lựa chọn cấu hình rồi tạo đối tượng hoàn chỉnh bằng `build()`. Một API dạng *fluent* thường cho phép gọi liên tiếp:

```java
new EmailBuilder()
        .text("Hello")
        .to("team@example.com")
        .build();
```

Nếu builder con kế thừa phương thức từ builder cha, thiết kế đơn giản sau gặp lỗi:

```java
class MessageBuilder {
    MessageBuilder text(String value) {
        return this;
    }
}

class EmailBuilder extends MessageBuilder {
    EmailBuilder to(String address) {
        return this;
    }
}

// Ví dụ lỗi biên dịch, không phải chương trình độc lập:
new EmailBuilder().text("Hello").to("team@example.com");
```

Mặc dù **đối tượng thực tế** vẫn là `EmailBuilder`, kiểu tĩnh của biểu thức sau `.text("Hello")` là `MessageBuilder` vì đó là kiểu trả về đã khai báo ở lớp cha. Lớp `MessageBuilder` không khai báo `to(...)`; trình biên dịch không thể gọi phương thức đó.

Đổi thứ tự thành `.to(...).text(...)` có thể biên dịch trong trường hợp này, nhưng không giải quyết vấn đề: sau khi gọi phương thức từ lớp cha, kiểu tĩnh bị thu hẹp về kiểu builder cha. Với nhiều tầng kế thừa, điều này gây lỗi ở các chuỗi lời gọi dài hơn.

**Mục tiêu của mẫu tự tham chiếu** là làm cho setter được định nghĩa trong lớp cha vẫn trả về **kiểu builder con cụ thể**, để có thể gọi tiếp setter của con theo bất kỳ thứ tự hợp lệ nào.

## 2. Giới hạn đệ quy và ý nghĩa của kiểu `SELF`

Giải pháp kinh điển dùng kiểu tham số tự tham chiếu (*self-referential generic type*, thường được gọi là **F-bounded polymorphism** hoặc mô phỏng *Curiously Recurring Template Pattern — CRTP*):

```java
abstract class BaseBuilder<SELF extends BaseBuilder<SELF>> {
    protected abstract SELF self();

    public SELF label(String value) {
        // Lưu value vào trạng thái của builder...
        return self();
    }
}

final class ConcreteBuilder extends BaseBuilder<ConcreteBuilder> {
    @Override
    protected ConcreteBuilder self() {
        return this;
    }
}
```

Phần quan trọng là:

```java
SELF extends BaseBuilder<SELF>
```

Đọc từng bước:

1. `BaseBuilder` có một tham số kiểu tên `SELF`.
2. `SELF` được giới hạn là một subtype của `BaseBuilder<SELF>`; giới hạn bên phải tiếp tục nhắc chính `SELF`, nên được gọi là **giới hạn đệ quy**.
3. Lớp cụ thể khai báo `extends BaseBuilder<ConcreteBuilder>`, khiến `SELF` tương ứng với `ConcreteBuilder` trong các phương thức được kế thừa.
4. Vì `label(...)` trả `SELF`, khi được gọi trên `ConcreteBuilder`, kiểu trả về lúc biên dịch là `ConcreteBuilder`.

Trong Java, ký hiệu `SELF` **không phải** từ khóa đặc biệt, cũng không phải một kiểu dựng sẵn. Có thể dùng `B`, `T`, `ThisBuilder`; điều quyết định là mối quan hệ đệ quy trong khai báo generic.

Ví dụ:

```java
ConcreteBuilder b = new ConcreteBuilder().label("x");
```

Biểu thức bên phải có kiểu `ConcreteBuilder` ngay tại thời điểm biên dịch.

### Vì sao cần `self()`?

Lớp cha chỉ biết `this` có kiểu tĩnh `BaseBuilder<SELF>`. Không thể mặc nhiên gán trực tiếp `this` cho biến kiểu `SELF`:

```java
// Trong BaseBuilder<SELF>:
public SELF label(String value) {
    return this; // Lỗi: this có kiểu BaseBuilder<SELF>, không chắc là SELF
}
```

Một số ví dụ dùng:

```java
@SuppressWarnings("unchecked")
protected SELF self() {
    return (SELF) this;
}
```

Đoạn này có **unchecked cast**: người viết API phải tự bảo đảm rằng đối tượng thực sự phù hợp với kiểu `SELF`. Sai kiểu tự tham chiếu có thể gây `ClassCastException` khi một client nhận giá trị trả về. Cách an toàn, dễ kiểm tra hơn trong hệ thống builder nhiều lớp là đặt `self()` thành `abstract` và để builder lá triển khai bằng `return this` **không cần cast**.

Giới hạn `SELF extends BaseBuilder<SELF>` giúp hạn chế những cách truyền tham số kiểu sai, nhưng **không chứng minh tuyệt đối** rằng `SELF` luôn chính là lớp runtime của `this`. Vì thế vẫn cần thiết kế hierarchy nhất quán và kiểm tra các lớp concrete.

## 3. Kế thừa nhiều tầng: giữ nguyên `SELF` xuyên suốt

Giả sử mô hình sản phẩm gồm:

```text
Message
  └── Email
       └── UrgentEmail
```

Mỗi sản phẩm có builder. Builder gốc cung cấp `text(...)`; builder của `Email` thêm `to(...)`; builder của `UrgentEmail` thêm `priority(...)`.

Ta muốn biểu thức sau **hợp lệ**:

```java
new UrgentEmail.Builder()
        .priority(2)
        .text("Alert")
        .to("admin@example.com")
        .build();
```

Điểm then chốt ở tầng trung gian là **truyền nguyên tham số `B` xuống lớp cha**:

```java
abstract static class Builder<B extends Builder<B>>
        extends Message.Builder<B> {
    // ...
}
```

Trong bối cảnh này, `Builder` là `Email.Builder`; ràng buộc `B extends Email.Builder<B>` cũng làm `B` tương thích với giới hạn `B extends Message.Builder<B>` của lớp cha. Khi builder lá là `UrgentEmail.Builder`, `B` được gắn với lớp lá đó trên **cả hai tầng**, nên `text(...)` và `to(...)` đều có kiểu trả về là `UrgentEmail.Builder`.

Một lỗi thường gặp là lớp trung gian quyết định trả về chính kiểu builder trung gian cố định, làm mất khả năng fluent của tầng kế tiếp. Nếu hierarchy vẫn sẽ có lớp con, hãy giữ builder trung gian **generic và abstract**, chỉ chốt kiểu tự tham chiếu ở builder concrete cuối cùng.

## 4. Ví dụ Java 17 hoàn chỉnh, biên dịch và chạy được

Tạo tệp **`BuilderInheritanceDemo.java`**:

```java
import java.util.Objects;

public class BuilderInheritanceDemo {
    static class Message {
        protected final String text;

        protected Message(Builder<?> builder) {
            this.text = Objects.requireNonNull(builder.text, "text");
        }

        public String summary() {
            return text;
        }

        static abstract class Builder<B extends Builder<B>> {
            private String text;

            public B text(String value) {
                this.text = Objects.requireNonNull(value, "text");
                return self();
            }

            protected abstract B self();

            public Message build() {
                return new Message(this);
            }
        }
    }

    static class Email extends Message {
        protected final String to;

        protected Email(Builder<?> builder) {
            super(builder);
            this.to = Objects.requireNonNull(builder.to, "to");
        }

        @Override
        public String summary() {
            return text + " -> " + to;
        }

        static abstract class Builder<B extends Builder<B>>
                extends Message.Builder<B> {
            private String to;

            public B to(String value) {
                this.to = Objects.requireNonNull(value, "to");
                return self();
            }

            @Override
            public Email build() {
                return new Email(this);
            }
        }
    }

    static final class UrgentEmail extends Email {
        private final int priority;

        private UrgentEmail(Builder builder) {
            super(builder);
            this.priority = builder.priority;
        }

        @Override
        public String summary() {
            return super.summary() + " [P" + priority + "]";
        }

        static final class Builder extends Email.Builder<Builder> {
            private int priority = 1;

            public Builder priority(int value) {
                if (value < 1) {
                    throw new IllegalArgumentException("priority must be positive");
                }
                this.priority = value;
                return this;
            }

            @Override
            protected Builder self() {
                return this;
            }

            @Override
            public UrgentEmail build() {
                return new UrgentEmail(this);
            }
        }
    }

    static final class PlainMessageBuilder
            extends Message.Builder<PlainMessageBuilder> {
        @Override
        protected PlainMessageBuilder self() {
            return this;
        }
    }

    static final class StandardEmailBuilder
            extends Email.Builder<StandardEmailBuilder> {
        @Override
        protected StandardEmailBuilder self() {
            return this;
        }
    }

    public static void main(String[] args) {
        Message plain = new PlainMessageBuilder()
                .text("Hi").build();

        Email standard = new StandardEmailBuilder()
                .text("Hello").to("team@example.com").build();

        UrgentEmail urgent = new UrgentEmail.Builder()
                .text("Outage").to("ops@example.com")
                .priority(1).build();

        UrgentEmail reverse = new UrgentEmail.Builder()
                .priority(2).to("admin@example.com")
                .text("Alert").build();

        System.out.println(plain.summary());
        System.out.println(standard.summary());
        System.out.println(urgent.summary());
        System.out.println(reverse.summary());
    }
}
```

Chạy từ thư mục chứa tệp:

```bash
javac --release 17 BuilderInheritanceDemo.java
java BuilderInheritanceDemo
```

Kết quả chính xác:

```text
Hi
Hello -> team@example.com
Outage -> ops@example.com [P1]
Alert -> admin@example.com [P2]
```

Ví dụ dùng lớp lồng tĩnh để gói toàn bộ source vào một tệp; trong ứng dụng thật, mỗi lớp sản phẩm có thể nằm ở tệp riêng với phạm vi truy cập phù hợp. Phần `main` chứng minh cả hai thứ tự: gọi setter lớp cha trước setter lớp con và ngược lại.

### 4.1. Đọc kiểu trả về của từng lời gọi

Với:

```java
UrgentEmail urgent = new UrgentEmail.Builder()
        .text("Outage")
        .to("ops@example.com")
        .priority(1)
        .build();
```

Trình biên dịch có thể nhìn các kiểu như sau:

| Biểu thức | Kiểu tĩnh |
| --- | --- |
| `new UrgentEmail.Builder()` | `UrgentEmail.Builder` |
| `.text("Outage")` | `UrgentEmail.Builder` |
| `.to("ops@example.com")` | `UrgentEmail.Builder` |
| `.priority(1)` | `UrgentEmail.Builder` |
| `.build()` | `UrgentEmail` |

Vì `UrgentEmail.Builder extends Email.Builder<UrgentEmail.Builder>` và tầng `Email.Builder<B> extends Message.Builder<B>`, setter `text` từ ông bà và setter `to` từ cha đều trả cùng kiểu `UrgentEmail.Builder`. Phương thức `build()` ở lớp lá ghi đè với kiểu trả về covariant `UrgentEmail`, cho phép gán trực tiếp, không cần cast.

### 4.2. Vì sao constructor nhận `Builder<?>`?

Trong ví dụ:

```java
protected Email(Builder<?> builder) {
    super(builder);
    this.to = Objects.requireNonNull(builder.to, "to");
}
```

`Email` chỉ cần **đọc trạng thái chung** từ một instance `Email.Builder` bất kỳ, không cần biết tham số `B` cụ thể. Vì vậy `Builder<?>` đủ biểu đạt mục đích. Trong `Message`, constructor tương tự nhận `Message.Builder<?>`; mọi `Email.Builder<B>` đều kế thừa từ `Message.Builder<B>`, nên đối số truyền vào `super(builder)` hợp lệ.

Dấu `?` tại constructor không phá suy luận kiểu của chuỗi fluent: nó chỉ xuất hiện ở vị trí **đọc state khi build**, không thay đổi kiểu trả về của các setter.

### 4.3. Tại sao `self()` chỉ triển khai ở builder lá?

`Message.Builder<B>` và `Email.Builder<B>` là `abstract`; chúng không cố trả về một kiểu builder cụ thể cho toàn bộ hậu duệ. Hai lớp concrete `PlainMessageBuilder`, `StandardEmailBuilder` và builder lồng trong `UrgentEmail` tự khai báo tham số generic của mình rồi `return this`.

Với mẫu này, mỗi builder cụ thể cần một triển khai `self()` rất ngắn, đổi lại tất cả setter được kế thừa trả đúng kiểu. Điều đó đặc biệt hữu ích khi số lượng thuộc tính chung nhiều hơn số lượng thuộc tính riêng của từng lớp con.

## 5. Những chỗ dễ nhầm giữa generics, override và constructor

### 5.1. `build()` và `self()` làm hai việc khác nhau

- `self()` trả về **builder** nhằm tiếp tục thiết lập thuộc tính.
- `build()` trả về **sản phẩm** đã được tạo.

Đoạn sau là hai lần trả về khác kiểu với mục đích khác nhau:

```java
@Override
protected UrgentEmail.Builder self() {
    return this;
}

@Override
public UrgentEmail build() {
    return new UrgentEmail(this);
}
```

Java cho phép `UrgentEmail build()` ghi đè `Email build()` vì `UrgentEmail extends Email`: đó là **covariant return type**. Cơ chế này độc lập với giới hạn đệ quy của `B`.

### 5.2. Đừng bỏ tham số kiểu ở lớp trung gian

Viết raw type:

```java
// Minh họa cách viết không nên dùng:
abstract static class Builder<B extends Builder<B>>
        extends Message.Builder {
}
```

sẽ đánh mất phần ràng buộc cần truyền xuống `Message.Builder`, tạo raw-type warnings, khiến chữ ký được kế thừa không còn giữ chính xác `B`. Trong hệ thống cần kiểu mạnh, hãy giữ:

```java
abstract static class Builder<B extends Builder<B>>
        extends Message.Builder<B> {
}
```

### 5.3. Đừng chốt builder cha thành một kiểu cụ thể quá sớm

Nếu `Email.Builder` là một lớp concrete trả `Email.Builder` trực tiếp từ `to(...)`, builder của `UrgentEmail` có thể mất quyền gọi `.priority(...)` ngay sau `.to(...)`. Builder tầng giữa cần tham số `B`, còn builder lá mới gắn `B = UrgentEmail.Builder`.

### 5.4. `return this` không tự động mang kiểu `B`

Lời gọi ở lớp generic:

```java
public B to(String value) {
    // ...
    return self(); // Đúng: phương thức abstract được builder lá triển khai
}
```

khác với `return this;` trong cùng lớp: `this` chỉ được biết là `Email.Builder<B>`, chưa chắc là `B`. Tránh ép `(B) this` để lấp chỗ trống mà không có bằng chứng về quan hệ runtime.

### 5.5. Tên builder và tầm nhìn truy cập

Trong ví dụ, có nhiều lớp tên `Builder` vì chúng là lớp lồng dưới `Message`, `Email`, `UrgentEmail`. Chúng là **các lớp khác nhau**, cần gọi đủ tên như `Email.Builder<B>` khi khai báo kế thừa. `private` của trường trong builder giúp giữ trạng thái đóng gói; constructor thuộc lớp bao có thể truy cập trường private của lớp lồng tương ứng theo quy tắc truy cập của Java.

Khi tách thành các class top-level ở các tệp riêng, phải thiết kế lại mức truy cập trường hoặc cung cấp accessor phù hợp; quyền truy cập private của một lớp lồng không tự suy rộng sang những lớp không cùng quan hệ lồng.

## 6. Trình tự thiết kế một hierarchy builder

Một cách làm ổn định là thiết kế từ hợp đồng sản phẩm đến builder:

1. **Vẽ cây lớp sản phẩm** và xác định thuộc tính chung / thuộc tính riêng. Nếu hai loại sản phẩm không thật sự có quan hệ `is-a`, cân nhắc composition.
2. Ở builder gốc, khai báo `abstract Builder<B extends Builder<B>>`, mỗi setter chung trả `B`, phần trả về gọi `self()`.
3. Ở builder trung gian còn cho phép kế thừa, khai báo `abstract Builder<B extends Builder<B>> extends Parent.Builder<B>`; các setter bổ sung cũng trả `B` bằng `self()`.
4. Ở builder lá, gắn chính lớp lá vào tham số generic: `extends Parent.Builder<ConcreteBuilder>`, triển khai `self() { return this; }`.
5. Nếu lớp sản phẩm lá có subtype hẹp hơn sản phẩm cha, ghi đè `build()` với kiểu trả về tương ứng.
6. Biên dịch các chuỗi gọi setter theo **nhiều thứ tự** và kiểm tra giá trị sản phẩm được tạo, thay vì chỉ thử thứ tự setter con trước cha.

Ví dụ một thử nghiệm kiểu hữu ích:

```java
// Trích từ ví dụ chạy được ở trên:
UrgentEmail.Builder b = new UrgentEmail.Builder()
        .text("A")
        .priority(3)
        .to("a@example.com");
```

Nếu dòng trên không biên dịch mà phải đổi `UrgentEmail.Builder b` thành `Email.Builder<?>`, hợp đồng fluent vẫn chưa giữ được kiểu cụ thể xuyên suốt.

## 7. Giới hạn và đánh đổi cần hiểu rõ

**Giới hạn đệ quy không có nghĩa Java có “self type” thực sự.** Cú pháp F-bound chủ yếu tạo quan hệ giữa các kiểu trong kiểm tra tĩnh. Nó không bắt buộc mọi subclass phải truyền chính bản thân làm `B` trong tất cả cấu trúc có thể viết, đặc biệt khi có hierarchy không `final` hoặc cố ý dùng cast. Vì vậy:

- Cho phép **builder trung gian** tiếp tục mở rộng bằng generic, nhưng thường đặt **builder lá** là `final` nếu không dự kiến có con tiếp theo.
- Viết `self()` cụ thể, chỉ trả `this` khi đối tượng có đúng kiểu được khai báo.
- Tránh raw type, unchecked cast hoặc trả về đối tượng builder khác trong `self()`.
- Đừng suy luận rằng một kiểu `B` có quan hệ F-bound bảo đảm được mọi invariant runtime về danh tính hoặc trạng thái.

**Builder thường có trạng thái mutable.** Fluent chaining cập nhật cùng một instance. Nếu lưu một builder để dùng lại, sản phẩm sau có thể mang cấu hình từ lần dùng trước. Không chia sẻ builder mutable giữa các thread trừ khi có chính sách đồng bộ hóa rõ ràng. Trong ví dụ, `Message`, `Email`, `UrgentEmail` giữ trường `final`, và constructor sao chép giá trị từ builder; việc sửa builder sau đó không đổi những trường này trong đối tượng đã tạo. Với danh sách, map hoặc đối tượng mutable khác, cần bản sao phòng vệ nếu muốn sản phẩm bất biến.

**Kiểm tra dữ liệu là trách nhiệm riêng.** Mẫu generic chỉ giải quyết kiểu của API fluent. Nó không bảo đảm `text` hoặc `to` được thiết lập; ví dụ gọi `Objects.requireNonNull` trong constructor để phát hiện thiếu giá trị và kiểm tra `priority > 0` trong setter. Một ứng dụng có thể dùng `build()` kiểm tra toàn bộ invariant và đưa thông báo lỗi phù hợp hơn.

**Cân nhắc độ phức tạp.** Với một hierarchy nhỏ, ghi đè covariant cho vài setter ở builder con cũng có thể đủ. F-bound phù hợp hơn khi có nhiều setter chung, nhiều builder con, hoặc nhiều tầng kế thừa. Nếu mô hình không cần subclass sản phẩm, builder đơn giản không generic thường dễ đọc và bảo trì hơn.

## 8. Các lỗi biên dịch và cách gỡ

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
| --- | --- | --- |
| `cannot find symbol` khi gọi setter con sau setter cha | Setter cha trả `ParentBuilder` | Cho setter cha trả `B`, và builder con truyền đúng `B` bằng F-bound. |
| `incompatible types: Parent.Builder<B> cannot be converted to B` | Trả `this` trong generic builder | Dùng `protected abstract B self()` với implementation ở builder lá. |
| `type argument ... is not within bounds` | Gắn sai tham số tự tham chiếu hoặc sai cấp builder | Kiểm tra `B extends Builder<B>` và đường kế thừa `extends Parent.Builder<B>`. |
| `name clash` hoặc không override được `build()` | Chữ ký phương thức/kiểu trả về không tương thích | Kiểm tra đúng phương thức và quy tắc covariant return; đừng thay đổi chỉ mỗi generic của kiểu sản phẩm tùy ý. |
| `ClassCastException` sau unchecked cast | `self()` ép sai kiểu runtime | Loại cast; triển khai `self()` cụ thể bằng `return this`; rà soát các lớp không `final`. |
| Dữ liệu null hoặc trạng thái không hợp lệ khi `build()` | Không có kiểm tra invariant | Validate trường bắt buộc, range của giá trị và sao chép mutable state khi cần. |

Nếu diagnostic của `javac` dài, hãy tìm phương thức được gọi **ngay trước khi kiểu bị mất** trong chuỗi. Có thể tách expression:

```java
UrgentEmail.Builder builder = new UrgentEmail.Builder();
UrgentEmail.Builder afterText = builder.text("Alert");
UrgentEmail.Builder afterTo = afterText.to("ops@example.com");
UrgentEmail result = afterTo.priority(2).build();
```

Cách viết tách dòng này buộc compiler đối chiếu từng kiểu mong đợi, rất hữu ích để xác định tầng generic nào không truyền tiếp `B`.

## 9. Bài luyện tập

**Bài 1 — tìm lỗi.** Vì sao cách viết sau không bảo đảm gọi được `.childOption()` sau `.common()`?

```java
class ParentBuilder {
    ParentBuilder common() {
        return this;
    }
}
class ChildBuilder extends ParentBuilder {
    ChildBuilder childOption() {
        return this;
    }
}
```

<details>
<summary>Đáp án</summary>

Vì `common()` khai báo trả `ParentBuilder`; kiểu tĩnh sau lời gọi không có `childOption()`. Đưa `ParentBuilder` thành generic `ParentBuilder<B extends ParentBuilder<B>>` với `common()` trả `B` và `self()`, rồi cho builder con truyền `ChildBuilder` làm tham số tự tham chiếu.

</details>

**Bài 2 — theo dấu kiểu.** Trong ví dụ chạy được, kiểu tĩnh sau `new UrgentEmail.Builder().text("X").to("y")` là gì? Phương thức nào cần được khai báo `abstract` để không phải cast trong các setter chung?

<details>
<summary>Đáp án</summary>

Kiểu là `UrgentEmail.Builder`. `Message.Builder<B>` khai báo `protected abstract B self()`; các builder lá thực hiện `self()` bằng `return this`. `Email.Builder<B>` tiếp tục kế thừa hợp đồng này mà không đóng `B` thành một lớp trung gian cố định.

</details>

**Bài 3 — mở rộng.** Thêm `final class ScheduledEmail extends Email` với builder lá `ScheduledEmail.Builder`, thuộc tính `scheduledAt` và setter trả đúng builder con. Cần thay đổi chữ ký `Email.Builder` không?

<details>
<summary>Định hướng</summary>

Giữ `Email.Builder<B extends Email.Builder<B>> extends Message.Builder<B>` như cũ. Builder mới khai báo `extends Email.Builder<ScheduledEmail.Builder>` (hoặc `extends Email.Builder<Builder>` khi `Builder` là lớp lồng), thêm setter `scheduledAt(...)`, triển khai `self()` và ghi đè `build()` trả `ScheduledEmail`. Constructor sản phẩm nhận builder đó và chuyển qua `super(builder)` để sử dụng thuộc tính chung.

</details>

## 10. Điểm cần nhớ

Với builder kế thừa, chìa khóa là **giữ kiểu builder lá qua mọi tầng**: lớp cha khai báo setter trả `B`, lớp trung gian chuyển `B` tiếp xuống cha, và lớp lá chọn chính nó làm `B`. `self()` cho setter trả đúng builder mà không cần unchecked cast; `build()` được override để tạo đúng loại sản phẩm.

Mẫu này xử lý vấn đề **kiểu tĩnh của fluent API**. Tính đúng đắn về validation, trạng thái mutable, bất biến của sản phẩm và lựa chọn kế thừa vẫn phải được thiết kế và kiểm thử riêng.