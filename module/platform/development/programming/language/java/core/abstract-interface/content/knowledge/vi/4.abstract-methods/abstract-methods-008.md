# Khai báo lại phương thức đã có thân thành `abstract` trong Java

Một phương thức đã có thân (concrete method) ở lớp cha **có thể được khai báo lại thành phương thức `abstract` ở một lớp con trừu tượng**, nếu phương thức của lớp cha có thể được override. Kỹ thuật này thường gọi là **re-abstracting a method** (tái trừu tượng hóa phương thức). Nó cho phép một nhánh kế thừa **không chấp nhận triển khai mặc định của lớp cha** và bắt buộc lớp con cụ thể ở nhánh đó tự chọn cách thực hiện.

Đây là một quy tắc dễ gây ngạc nhiên: một lớp cha cung cấp đầy đủ thân phương thức **không có nghĩa** mọi lớp con trong mọi nhánh đều phải kế thừa phần cài đặt ấy. Lớp con `abstract` có thể loại bỏ việc kế thừa triển khai cho một phương thức bằng cách khai báo override trừu tượng.

## 1. Cấu trúc và điều kiện cần

Mẫu cơ bản:

```java
class Parent {
    public void execute() {
        System.out.println("Cách làm mặc định");
    }
}

abstract class MustImplement extends Parent {
    @Override
    public abstract void execute();
}

class ConcreteChild extends MustImplement {
    @Override
    public void execute() {
        System.out.println("Cách làm được chọn rõ ràng");
    }
}
```

Ở đây:

- `Parent.execute()` là **concrete method**: có thân, đối tượng `Parent` gọi được ngay.
- `MustImplement` là **abstract class**. Dòng `public abstract void execute();` override phương thức của `Parent` nhưng cố ý **không có thân**. `@Override` hợp lệ và giúp trình biên dịch kiểm tra đây đúng là override.
- `ConcreteChild` là lớp cụ thể: phải cung cấp triển khai `execute()` hợp lệ mới tạo được đối tượng.
- Một lớp con khác của `Parent` mà **không** đi qua `MustImplement` vẫn được dùng `Parent.execute()` mặc định.

Dấu chấm phẩy `;` sau khai báo abstract là bắt buộc; không đặt cặp ngoặc `{}` vào phương thức `abstract` ngay cả khi thân rỗng. `abstract` ở đây đánh dấu yêu cầu triển khai, không phải phương thức có thân rỗng.

Quan trọng: **không thể khai báo hai phương thức cùng chữ ký trong cùng một lớp**, một concrete rồi một abstract. Re-abstract là việc **override phương thức được thừa kế từ lớp cha**, không phải tạo hai phương thức cùng tên/cùng tham số ngay trong một lớp.

## 2. Vì sao cần làm vậy?

Giả sử thư viện có lớp `Formatter` với cách định dạng chung. Một nhóm ứng dụng mới yêu cầu mỗi bộ định dạng phải chọn cách trình bày riêng; dùng ngầm cách mặc định có nguy cơ sai quy tắc nghiệp vụ.

Ta có ba lựa chọn:

1. Giữ `Formatter` để những trường hợp cũ vẫn dùng triển khai mặc định.
2. Tạo `StrictFormatter extends Formatter`, khai báo lại `render(...)` thành `abstract` để **mọi lớp cụ thể kế thừa qua nhánh này phải cài đặt**.
3. Cho từng lớp cụ thể như `UpperFormatter` hoặc `SlugFormatter` triển khai `render(...)`.

Nhờ vậy, thay đổi yêu cầu chỉ ảnh hưởng **nhánh kế thừa nghiêm ngặt**. Ta không cần xóa thân phương thức ở `Formatter` và không phải buộc mọi lớp con hiện hữu thực hiện lại hành vi cũ. Kỹ thuật này hữu ích khi thiết kế khung mở rộng, chuyển tiếp API cũ hoặc dùng một lớp cơ sở có tiện ích chung nhưng muốn một nhánh bắt buộc cung cấp hành vi cụ thể.

Tuy nhiên, re-abstract không phải mặc định tốt cho mọi thiết kế. Nếu không có quan hệ kế thừa thực sự giữa các loại đối tượng, interface và composition thường dễ tổ chức hơn.

## 3. Ví dụ Java 17 chạy hoàn chỉnh

Lưu toàn bộ chương trình sau thành **`Main.java`**:

```java
import java.util.Locale;

public class Main {
    static class Formatter {
        public String render(String input) {
            return "DEFAULT(" + input + ")";
        }

        public final String describe(String input) {
            return "Result=" + render(input);
        }
    }

    static abstract class StrictFormatter extends Formatter {
        @Override
        public abstract String render(String input);
    }

    static final class UpperFormatter extends StrictFormatter {
        @Override
        public String render(String input) {
            return "UPPER(" + input.toUpperCase(Locale.ROOT) + ")";
        }
    }

    static final class SlugFormatter extends StrictFormatter {
        @Override
        public String render(String input) {
            return "SLUG(" + input.toLowerCase(Locale.ROOT)
                    .replace(' ', '-') + ")";
        }
    }

    public static void main(String[] args) {
        Formatter[] formatters = {
                new Formatter(),
                new UpperFormatter(),
                new SlugFormatter()
        };

        for (Formatter formatter : formatters) {
            System.out.println(formatter.describe("Java 17"));
        }
    }
}
```

Với JDK 17 trở lên, thực hiện trong thư mục chứa `Main.java`:

```bash
javac Main.java
java Main
```

**Kết quả chuẩn:**

```text
Result=DEFAULT(Java 17)
Result=UPPER(JAVA 17)
Result=SLUG(java-17)
```

**Giải thích kết quả theo thứ tự chạy:**

1. Phần tử `new Formatter()` sử dụng `Formatter.render()` đã có thân; nhận `DEFAULT(Java 17)`.
2. Phần tử `new UpperFormatter()` có nhánh kế thừa `Formatter → StrictFormatter → UpperFormatter`. `StrictFormatter` đã khai báo lại `render()` là abstract, nên `UpperFormatter` phải định nghĩa phương thức và trả `UPPER(JAVA 17)`.
3. Phần tử `new SlugFormatter()` thuộc cùng nhánh, cũng phải định nghĩa `render()`, trả `SLUG(java-17)`.
4. Dù biến trong vòng lặp có kiểu `Formatter`, lời gọi `render()` bên trong `Formatter.describe()` được **dispatch động** theo loại đối tượng thực tế. Do đó `describe()` có thể dùng một lần cài đặt chung mà vẫn nhận cách định dạng khác nhau.
5. `describe()` được khai báo `final`, nên các lớp con không thể override bản thân nó; ví dụ vẫn re-abstract được `render()` vì **`render()` không `final`**.

Lưu ý: `StrictFormatter` **không tự tạo đối tượng được** do nó là `abstract class`. Một lớp cụ thể đi qua `StrictFormatter` cũng không thể “dùng lại mặc định” chỉ bằng cách bỏ qua `render()` vì yêu cầu abstract của lớp trung gian vẫn còn hiệu lực.

## 4. Chính xác phần nào của kế thừa thay đổi?

Phân biệt **hợp đồng phương thức** với **thân phương thức**:

| Loại lớp | Tình trạng của `render(String)` | Có thể `new`? | Khi chạy |
| --- | --- | --- | --- |
| `Formatter` | Concrete, có thân mặc định | Có | Dùng `DEFAULT(...)` |
| `StrictFormatter` | Override thành abstract, không có thân | Không | Chưa có cài đặt ở nhánh này |
| `UpperFormatter` | Override thành concrete | Có | Dùng `UPPER(...)` |
| `SlugFormatter` | Override thành concrete | Có | Dùng `SLUG(...)` |

Có thể mô tả nhánh kế thừa như sau:

```text
Formatter
  ├─ render(String): concrete
  └─ StrictFormatter (abstract)
       ├─ render(String): abstract  ← tái trừu tượng hóa
       ├─ UpperFormatter
       │    └─ render(String): concrete
       └─ SlugFormatter
            └─ render(String): concrete
```

Việc re-abstract **không xóa** mã của `Formatter.render()` khỏi lớp gốc: một đối tượng `Formatter` hoặc nhánh kế thừa khác không override vẫn gọi được nó. Tuy nhiên, đối với một lớp con kế thừa thông qua `StrictFormatter`, phương thức được thừa kế trong nhánh này là khai báo `abstract` gần nhất và lớp cụ thể phải đáp ứng yêu cầu đó.

`@Override` không phải yếu tố làm phương thức trở thành abstract; từ khóa `abstract` mới quyết định điều đó. `@Override` được khuyên dùng để bắt lỗi chính tả/tên/tham số khi chủ đích là override.

## 5. Quy tắc về chữ ký và phạm vi truy cập

Phương thức khai báo lại phải tuân theo quy tắc override bình thường của Java:

- **Tên và danh sách tham số:** chữ ký override tương ứng phương thức được kế thừa; thay đổi tham số sẽ tạo overload, không ép lớp con triển khai phương thức cũ.
- **Kiểu trả về:** giữ kiểu tương thích (có thể dùng kiểu trả về hiệp biến cho kiểu tham chiếu). Không thay bằng kiểu không tương thích.
- **Mức truy cập:** không giảm khả năng truy cập của phương thức gốc. Phương thức cha `public` phải được override bằng `public`.
- **Checked exceptions:** phương thức override không được khai báo checked exception rộng hơn những gì phương thức cha cho phép; exception không kiểm tra (`RuntimeException` và lớp con) chịu quy tắc khác.
- **`final` / `static` / `private`:** `final` cấm override; `static` dùng cơ chế che khuất (hiding), không phải override instance method; `private` không được thừa kế làm một phương thức có thể override theo cách này.
- **Phương thức `abstract` không thể đồng thời `final`, `static`, `private`**. Bản khai báo abstract không có thân, còn `final` lại cấm ghi đè để cung cấp thân.

Ví dụ hợp lệ với phạm vi truy cập và kiểu trả về hiệp biến (đây là đoạn minh họa độc lập về quan hệ kiểu, không phải phần của chương trình `Main.java` ở trên):

```java
class Metric {
    protected Number value() {
        return 1;
    }
}

abstract class ExactMetric extends Metric {
    @Override
    protected abstract Integer value();
}

class CountMetric extends ExactMetric {
    @Override
    protected Integer value() {
        return 5;
    }
}
```

`Integer` là subtype của `Number`, nên `ExactMetric.value()` có kiểu trả về tương thích và việc override hợp lệ.

## 6. Những ví dụ không biên dịch được và lý do

Các đoạn dưới đây minh họa **lỗi cố ý**, không ghép vào `Main.java` đang chạy.

**Lỗi 1 — lớp cụ thể không hiện thực phương thức vừa được re-abstract:**

```java
class IncompleteFormatter extends StrictFormatter {
    // Không override render(String): lỗi biên dịch.
}
```

Nếu muốn giữ lớp này không có cài đặt, phải khai báo nó `abstract`, khi đó vẫn không thể `new IncompleteFormatter()`. Nếu muốn tạo đối tượng, nó phải hiện thực `render(String)` trực tiếp hoặc kế thừa một cài đặt concrete hợp lệ từ một lớp phù hợp trong chuỗi kế thừa.

**Lỗi 2 — cố re-abstract một phương thức `final`:**

```java
class LockedParent {
    public final void save() {
        System.out.println("đã lưu");
    }
}

abstract class InvalidChild extends LockedParent {
    @Override
    public abstract void save(); // Lỗi: không thể override final.
}
```

Từ khóa `final` ở lớp cha cấm bất kỳ override nào, kể cả khai báo abstract.

**Lỗi 3 — dùng `static` như một phương thức có thể override:**

```java
class Utility {
    public static void run() {}
}

abstract class InvalidUtility extends Utility {
    @Override
    public abstract void run(); // Lỗi: instance method không override static.
}
```

Phương thức static gắn với lớp, không tham gia dynamic dispatch như instance method. Khai báo lại bằng phương thức abstract instance là xung đột.

**Lỗi 4 — khai báo abstract và concrete trùng chữ ký trong cùng lớp:**

```java
abstract class Wrong {
    public void work() {}
    public abstract void work(); // Lỗi: cùng chữ ký trong một lớp.
}
```

Re-abstract phải diễn ra **giữa các lớp trong quan hệ kế thừa**, không phải thông qua hai khai báo trùng nhau trong một lớp.

**Lỗi 5 — gọi `super.render()` từ lớp cháu để lấy lại thân gốc:**

```java
class BrokenFormatter extends StrictFormatter {
    @Override
    public String render(String input) {
        return super.render(input); // Lỗi: render trong StrictFormatter là abstract.
    }
}
```

`super` ở đây tham chiếu triển khai ở lớp cha trực tiếp theo quy tắc gọi `super`; lời gọi tới phương thức abstract đó không cung cấp được thân để thực thi. Java không hỗ trợ cú pháp `super.super.render(...)` nhằm “nhảy qua” `StrictFormatter`. Nếu muốn cho phép dùng lại logic mặc định, hãy **thiết kế rõ một helper concrete riêng** ở lớp gốc (chẳng hạn `protected final String renderDefault(String input)`) để các lớp con gọi helper đó.

## 7. Phân biệt re-abstract, override thông thường và overload

| Hành động | Ví dụ | Kết quả |
| --- | --- | --- |
| Override concrete bằng concrete | Lớp con `public String render(...){...}` | Đưa ra triển khai mới |
| **Re-abstract concrete bằng abstract** | Lớp con abstract `public abstract String render(...);` | Buộc lớp cụ thể ở nhánh sau hiện thực |
| Kế thừa không override | Lớp con giữ nguyên `render()` của cha | Dùng triển khai hiện có |
| Overload | Thêm `render(String, boolean)` | Tạo chữ ký khác, không đáp ứng hay thay thế `render(String)` |

Đa hình runtime vẫn phát huy tác dụng sau khi lớp cụ thể cung cấp thân mới. Re-abstract chủ yếu là **ràng buộc tại lúc biên dịch**: nó buộc người xây dựng lớp cụ thể phải quyết định hành vi thay vì vô tình kế thừa mặc định.

### Trường hợp interface có phương thức `default`

Có một ý tưởng tương tự trong kế thừa **interface**. Interface con có thể ghi đè một `default` method được kế thừa bằng một khai báo abstract để yêu cầu implementer cung cấp lại:

```java
interface Greeter {
    default String greet() {
        return "Xin chào mặc định";
    }
}

interface CustomGreeter extends Greeter {
    @Override
    String greet();
}

class FriendlyGreeter implements CustomGreeter {
    @Override
    public String greet() {
        return "Xin chào từ lớp triển khai";
    }
}
```

Đoạn này minh họa quan hệ interface, **không phải** abstract class. `Greeter` gốc vẫn giữ default method; nhưng một lớp cụ thể `implements CustomGreeter` phải đáp ứng `greet()` theo hợp đồng ở interface con. Không nên nhầm `default` method trong interface với phương thức `static` hoặc một trường hợp Java cho phép đa kế thừa lớp.

## 8. Khi nào nên dùng, khi nào không?

**Nên cân nhắc re-abstract khi:**

- Lớp cơ sở có một hành vi mặc định hợp lý cho đa số trường hợp.
- Một nhánh kế thừa đặc biệt có quy tắc chặt chẽ: mỗi lớp cụ thể bắt buộc chọn hành vi riêng.
- Bạn cần giữ API và hành vi cũ ở lớp cơ sở, đồng thời bắt buộc nhánh mới cung cấp implementation.
- Lớp trung gian trừu tượng có vai trò thiết kế rõ ràng và thực sự biểu diễn quan hệ “là một” (`is-a`).

**Nên cân nhắc interface/composition thay thế khi:**

- Các đối tượng chỉ có chung khả năng, không có quan hệ kế thừa lớp có ý nghĩa.
- Cần thay chiến lược ở thời điểm chạy bằng cách truyền dependency khác, thay vì cố định theo cây kế thừa.
- Cây lớp ngày càng sâu, khó giải thích vì sao một nhánh cấm triển khai mặc định.
- Chỉ cần sửa một lời gọi nhỏ trong hệ thống hiện tại và không muốn thêm một abstract layer không mang ràng buộc hữu ích.

Chọn re-abstract là một **quyết định về hợp đồng kế thừa**. Nếu mục tiêu đơn thuần là đưa nhiều thuật toán dưới cùng một kiểu sử dụng, một interface chung và các implementation độc lập có thể sáng rõ hơn.

## 9. Câu hỏi tự kiểm tra

1. Trong ví dụ, vì sao `new Formatter()` hợp lệ nhưng `new StrictFormatter()` không hợp lệ?
2. Điều gì khiến `UpperFormatter` bắt buộc cài đặt `render()`, dù `Formatter` đã có thân?
3. Có thể re-abstract `Formatter.describe()` không? Từ khóa nào quyết định câu trả lời?
4. Nếu tạo `class LegacyChild extends Formatter {}`, kết quả `new LegacyChild().render("Java")` sẽ là gì?
5. Vì sao phương thức `render(String, boolean)` không thay thế việc override `render(String)`?
6. Muốn triển khai mới tái sử dụng phần logic của `Formatter.render()`, thiết kế helper như thế nào để không dùng cú pháp `super.super`?
7. Trong một thiết kế không có quan hệ cha–con tự nhiên, vì sao interface hoặc composition có thể tốt hơn lớp trung gian re-abstract?

**Điểm cần nhớ:** Java cho phép một **abstract subclass override một instance method concrete có thể override của superclass bằng abstract method**. Điều này giữ nguyên hành vi mặc định ở lớp gốc, nhưng tạo nghĩa vụ triển khai mới cho các lớp cụ thể trong một nhánh kế thừa. Quy tắc override thông thường vẫn áp dụng, đặc biệt đối với `final`, `static`, `private`, kiểu trả về và mức truy cập.
