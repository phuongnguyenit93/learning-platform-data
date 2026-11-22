# Quan hệ giữa phương thức `abstract` và lớp chứa nó trong Java

Một phương thức `abstract` mô tả **một hành vi mà kiểu cha yêu cầu nhưng chưa cung cấp phần thân thực thi**. Quan hệ giữa phương thức này và kiểu chứa nó quyết định kiểu nào phải khai báo `abstract`, kiểu nào được phép khởi tạo đối tượng và lớp con nào có trách nhiệm hiện thực hành vi.

## 1. Quy tắc cốt lõi

Với **lớp (`class`) thông thường trong Java**:

- Nếu lớp **trực tiếp khai báo ít nhất một phương thức `abstract`**, bản thân lớp **bắt buộc phải được khai báo `abstract`**.
- Chiều ngược lại **không đúng**: một `abstract class` hoàn toàn có thể **không có phương thức `abstract` nào**. Người thiết kế vẫn có thể dùng nó để ngăn khởi tạo trực tiếp hoặc làm lớp nền cho hệ phân cấp.
- Một lớp không có từ khóa `abstract` (**concrete class**) phải cung cấp hoặc kế thừa triển khai hợp lệ cho **tất cả phương thức abstract còn tồn đọng** trong hệ phân cấp kiểu của nó. Nếu chưa đáp ứng được, lớp đó phải là `abstract class`.
- Không thể tạo đối tượng trực tiếp bằng `new` từ `abstract class`, dù lớp ấy có constructor và dù chưa khai báo phương thức abstract nào. Tuy nhiên, constructor của lớp abstract vẫn được gọi trong quá trình khởi tạo đối tượng lớp con.
- `abstract` thuộc về **phương thức cần triển khai** và **lớp chưa hoàn chỉnh để khởi tạo**, nhưng hai khái niệm không đồng nghĩa: `abstract class` có thể chứa phương thức đã có thân, trường dữ liệu, constructor, phương thức `static` và `final`.

Trong một `interface`, phương thức thể hiện hợp đồng và không có phần thân thường **ngầm định `public abstract`**. Interface không được khai báo bằng `abstract class`; nó là loại kiểu riêng. Trường hợp `enum` có phương thức abstract là ngoại lệ chuyên biệt, được minh họa ở phần 8.

## 2. Ví dụ một lớp vừa có hợp đồng abstract vừa có logic dùng chung

```java
abstract class DocumentJob {
    protected abstract String execute();

    public String report() {
        return "Result: " + execute();
    }
}
```

`DocumentJob` cần từ khóa `abstract` vì trực tiếp khai báo `execute()` không có thân. Phương thức `report()` đã có triển khai và được phép gọi `execute()`; khi một đối tượng lớp con cụ thể chạy `report()`, lời gọi `execute()` sử dụng implementation tương ứng với lớp thực tế. Điều này cho phép lớp nền giữ một phần quy trình chung và yêu cầu lớp con hoàn thành một bước còn thiếu.

Việc `execute()` không có thân là quy tắc cú pháp của abstract method; còn việc lớp chứa bắt buộc abstract là quy tắc **ở cấp class**. Một `abstract class` không khai báo bất kỳ phương thức abstract nào vẫn hợp lệ: nó có thể chỉ giữ constructor, dữ liệu chung hoặc cố ý ngăn tạo instance trực tiếp. Phần cú pháp với dấu `;` và `interface` được trình bày riêng ở bài mở đầu chương.

## 3. Hai chiều quan hệ không tương đương

| Tình huống | Có hợp lệ? | Lý do |
| --- | --- | --- |
| `abstract class A { abstract void run(); }` | Có | Lớp được đánh dấu abstract để chứa phương thức abstract. |
| `abstract class A { void run() {} }` | Có | Lớp abstract không bắt buộc khai báo phương thức abstract. |
| `class A { abstract void run(); }` | Không | Lớp cụ thể trực tiếp khai báo phương thức abstract. |
| `class A { void run() {} }` | Có | Lớp cụ thể có triển khai đầy đủ. |
| `abstract final class A {}` | Không | `abstract` cần cho phép tạo lớp con triển khai; `final` cấm kế thừa. |
| `abstract class A { private abstract void run(); }` | Không | `private` mâu thuẫn với hợp đồng ghi đè của phương thức abstract. |

Bảng xem xét các khai báo `class` thông thường; `interface` và `enum` có quy tắc cú pháp riêng.

Phân biệt thêm:

- **Phương thức abstract**: thiếu phần thân tại nơi khai báo, tạo nghĩa vụ triển khai trong lớp con cụ thể.
- **Lớp abstract**: chưa được phép khởi tạo trực tiếp; có thể chứa hoặc thừa hưởng những nghĩa vụ triển khai, hoặc chỉ đóng vai trò lớp nền.
- **Lớp concrete**: có thể khởi tạo nếu constructor khả dụng và mọi hợp đồng phương thức abstract đã được thực hiện hợp lệ.

Vì vậy câu “lớp abstract thì tất cả phương thức đều abstract” là sai; câu “có phương thức abstract thì lớp chứa là abstract” đúng với khai báo `class` thông thường nhưng phải xét riêng `interface` và `enum`.

## 4. Quan hệ với lớp con: kế thừa, triển khai và khởi tạo

Một phương thức abstract trong lớp cha được **kế thừa như một nghĩa vụ**. Lớp con có hai hướng xử lý:

1. **Lớp con vẫn là abstract**: được phép chưa triển khai phương thức. Nó có thể tiếp tục chuyển nghĩa vụ xuống các lớp con sau.
2. **Lớp con là concrete**: phải tự triển khai phương thức abstract còn thiếu, hoặc kế thừa một triển khai concrete hợp lệ đã có từ hệ phân cấp.

Khi ghi đè, nên dùng `@Override` để trình biên dịch kiểm tra chữ ký. Triển khai phải tuân thủ quy tắc override: không giảm mức truy cập, kiểu trả về tương thích (bao gồm kiểu trả về đồng biến nếu áp dụng), không mở rộng checked exception vượt khai báo của phương thức được ghi đè.

Sơ đồ tư duy:

```text
abstract class Ticket
  ├─ constructor, field, phương thức có thân header()
  └─ abstract int fee()
          ↓ kế thừa nghĩa vụ
final class AdultTicket extends Ticket
  └─ @Override int fee() { ... }
          ↓
Có thể khởi tạo new AdultTicket(...)
Có thể gán tham chiếu Ticket để gọi fee() đa hình
```

### Ví dụ 1: lớp cha abstract, lớp con concrete

Lưu toàn bộ ví dụ sau trong tệp `AbstractMethodDemo.java`:

```java
abstract class Ticket {
    private final String holder;

    protected Ticket(String holder) {
        this.holder = holder;
    }

    public String header() {
        return "Ticket for " + holder;
    }

    public abstract int fee();
}

final class AdultTicket extends Ticket {
    AdultTicket(String holder) {
        super(holder);
    }

    @Override
    public int fee() {
        return 100;
    }
}

public class AbstractMethodDemo {
    public static void main(String[] args) {
        Ticket ticket = new AdultTicket("Lan");

        System.out.println(ticket.header());
        System.out.println("Fee: " + ticket.fee());
    }
}
```

Biên dịch và chạy bằng Java 17+:

```bash
javac -encoding UTF-8 AbstractMethodDemo.java
java AbstractMethodDemo
```

Kết quả:

```text
Ticket for Lan
Fee: 100
```

Điều cần quan sát:

- `Ticket` **không thể khởi tạo trực tiếp**, do được khai báo `abstract`.
- `Ticket` vẫn được phép có trường `holder`, constructor và phương thức cụ thể `header()`.
- `AdultTicket` trở thành lớp cụ thể vì nó cung cấp `fee()` đúng hợp đồng.
- Biến `ticket` có kiểu tham chiếu `Ticket` nhưng đối tượng thực tế là `AdultTicket`; lời gọi `ticket.fee()` chạy triển khai trong `AdultTicket` theo cơ chế **dynamic dispatch**.
- Từ khóa `final` trên `AdultTicket` chỉ ngăn tạo lớp con tiếp theo; nó hợp lệ ở đây vì `AdultTicket` không phải lớp abstract.

### Ví dụ 2: lớp con trung gian vẫn abstract

Lưu toàn bộ ví dụ trong `InheritanceDemo.java`:

```java
abstract class Device {
    public abstract String connect();
}

abstract class NetworkDevice extends Device {
    public String category() {
        return "Network device";
    }
    // Chưa triển khai connect(): hợp lệ vì lớp vẫn abstract.
}

final class WifiDevice extends NetworkDevice {
    @Override
    public String connect() {
        return "Connected by WiFi";
    }
}

public class InheritanceDemo {
    public static void main(String[] args) {
        Device device = new WifiDevice();
        System.out.println(device.connect());
    }
}
```

```bash
javac -encoding UTF-8 InheritanceDemo.java
java InheritanceDemo
```

```text
Connected by WiFi
```

`NetworkDevice` không cần lặp lại dòng `abstract String connect();`. Nghĩa vụ triển khai vẫn được kế thừa từ `Device` và chuyển tiếp cho `WifiDevice`. Nếu bỏ phương thức `connect()` khỏi `WifiDevice` mà vẫn giữ lớp concrete, chương trình sẽ không biên dịch.

## 5. Nếu lớp chứa không khai báo phương thức abstract trực tiếp thì sao?

Quy tắc phải xét **toàn bộ phương thức abstract còn chưa được triển khai**, gồm cả phương thức kế thừa từ lớp cha và từ interface.

```java
interface Identifiable {
    String id();
}

abstract class BaseEntity implements Identifiable {
    // Không khai báo lại id(); vẫn có nghĩa vụ từ interface.
}

final class UserEntity extends BaseEntity {
    @Override
    public String id() {
        return "U-001";
    }
}
```

Đoạn trên là minh họa các khai báo kiểu (không có `main`). `BaseEntity` phải tiếp tục là abstract vì chưa triển khai `id()`. `UserEntity` đáp ứng nghĩa vụ bằng một phương thức `public`.

Ngược lại, nếu `BaseEntity` đã cung cấp phương thức `public String id()` có thân phù hợp, `UserEntity` có thể kế thừa triển khai đó mà không phải ghi đè thêm.

Một lớp con **không được phép chỉ thêm từ khóa `abstract` cho phương thức nhưng tự giữ lớp concrete**. Nghĩa vụ luôn đi cùng trạng thái abstract của lớp chưa hoàn chỉnh.

## 6. Nghĩa vụ đến từ interface và abstract class

Không chỉ phương thức abstract **tự khai báo** trong lớp mới tạo nghĩa vụ. Khi một abstract class `implements` interface nhưng chưa cung cấp phương thức cụ thể, nó được phép chuyển nghĩa vụ cho lớp con. Trường hợp `BaseEntity implements Identifiable` ở mục 5 minh họa chính xác điều này.

| Khía cạnh | `abstract class` | `interface` |
|---|---|---|
| Khai báo phương thức abstract | Ghi `abstract`; có thể `public`, `protected` hoặc package-private | Phương thức instance không có thân mặc định `public abstract` |
| Vai trò đối với lớp concrete | Phải hoàn tất mọi hợp đồng abstract kế thừa còn thiếu | Lớp `implements` phải hoàn tất mọi hợp đồng chưa có implementation phù hợp |
| Thành viên dùng chung | Có constructor, state instance và phương thức concrete | Có `default`/`static`/`private` method theo quy tắc riêng; không có constructor instance |
| Giới hạn kế thừa trực tiếp | Chỉ được `extends` một class | Có thể `implements` nhiều interface |

**Điều kiện quan trọng:** một method có cùng tên chưa chắc đã thực hiện nghĩa vụ. Cần đối chiếu chữ ký, kiểu trả về, ngoại lệ và phạm vi truy cập, đặc biệt khi lớp con nằm khác package. Một concrete method được kế thừa hợp lệ có thể đáp ứng hợp đồng mà không cần viết lại override. Ngược lại, một default method của interface không phải lúc nào cũng thắng phương thức kế thừa từ class; Java áp dụng quy tắc giải quyết xung đột theo hệ phân cấp. Các bài sau đi sâu vào từng ngoại lệ.

## 7. Chẩn đoán lớp concrete chưa hoàn tất hợp đồng

Khi compiler báo lớp con chưa thực hiện abstract method, hãy tìm **phương thức còn thiếu**, thay vì mặc định rằng thiếu từ khóa `abstract` ở lớp chứa.

| Hiện tượng | Câu hỏi cần kiểm tra | Hướng sửa |
|---|---|---|
| Lớp concrete chưa implement đủ | Có abstract method nào được kế thừa từ class hoặc interface? | Thêm implementation hợp lệ hoặc giữ lớp con là `abstract` |
| Có method trùng tên nhưng vẫn báo thiếu | Danh sách kiểu tham số có khác không? | Dùng `@Override` để phát hiện overload ngoài ý muốn |
| Có implementation nhưng compiler báo quyền truy cập yếu hơn | Lớp cha hoặc interface yêu cầu `public`/`protected`? | Giữ hoặc mở rộng visibility theo quy tắc override |
| Lớp con khác package không implement được hook | Hook ở lớp cha có phải package-private? | Dùng `protected`/`public` nếu cần mở rộng xuyên package hoặc hoàn tất hook trong package gốc |
| Chưa thể tạo instance của lớp nền | Bản thân lớp vẫn được khai báo `abstract`? | Tạo đối tượng từ một lớp concrete phù hợp |

Khai báo `private abstract`, `static abstract`, `final abstract` và đặt thân `{ ... }` cho abstract method là các lỗi cú pháp/modifier riêng. Những ví dụ sai cùng cách sửa chi tiết nằm ở các bài chuyên về cú pháp và modifier; chúng không thay đổi quy tắc kế thừa nghĩa vụ ở đây.

## 8. Các điểm tinh tế cần nhớ

### 8.1. Lớp abstract không phải “lớp không có constructor”

Lớp abstract có thể khai báo constructor để khởi tạo trạng thái chung. Constructor được chạy khi tạo đối tượng của lớp con; chỉ thao tác `new AbstractBase()` trực tiếp là không hợp lệ. Không thể khai báo constructor là `abstract`, vì constructor không được ghi đè như phương thức instance.

Tránh gọi trực tiếp phương thức có thể bị override (đặc biệt phương thức abstract) từ constructor của lớp cha: lời gọi có thể dispatch tới lớp con **trước khi các trường khởi tạo riêng của lớp con sẵn sàng**, tạo ra lỗi trạng thái khó phát hiện.

### 8.2. Lớp abstract có thể khai báo lại phương thức đã có thân thành abstract

Trong một **lớp con abstract**, đôi khi người thiết kế muốn buộc lớp con tiếp theo tự quyết định lại hành vi dù lớp cha đã có triển khai:

```java
class BaseNotifier {
    public void notifyUser() {
        System.out.println("Generic");
    }
}

abstract class CustomNotifier extends BaseNotifier {
    @Override
    public abstract void notifyUser();
}
```

Đây là khai báo hợp lệ: `CustomNotifier` biến yêu cầu `notifyUser()` thành abstract đối với lớp con cụ thể của nó, miễn tuân thủ quy tắc override. Đoạn code là minh họa khai báo, không chứa `main`.

### 8.3. Trường hợp đặc biệt: enum có phương thức abstract

Một `enum` có thể khai báo phương thức instance abstract nếu **mọi hằng enum cung cấp triển khai** thông qua thân lớp riêng của hằng. Không viết `abstract enum`. Ví dụ hoàn chỉnh trong `EnumAbstractDemo.java`:

```java
enum Level {
    LOW {
        @Override
        int score() {
            return 1;
        }
    },
    HIGH {
        @Override
        int score() {
            return 10;
        }
    };

    abstract int score();
}

public class EnumAbstractDemo {
    public static void main(String[] args) {
        System.out.println(Level.HIGH.score());
    }
}
```

```bash
javac -encoding UTF-8 EnumAbstractDemo.java
java EnumAbstractDemo
```

```text
10
```

Đây là trường hợp đặc biệt của Java cho thấy quy tắc “cứ có phương thức abstract thì phải viết `abstract class`” chỉ áp dụng trực tiếp cho khai báo `class` thông thường, không được máy móc áp vào interface hoặc enum.

## 9. Chọn abstract class hay interface khi thiết kế?

Khi chỉ cần quy định **những hành vi mà nhiều lớp không có chung tổ tiên vẫn thực hiện được**, interface thường là lựa chọn tự nhiên. Khi cần **chia sẻ trạng thái, constructor, logic chung** và để một số bước cho lớp con quyết định, abstract class phù hợp hơn. Một lớp Java chỉ được `extends` trực tiếp một lớp cha nhưng có thể `implements` nhiều interface.

Dù chọn cách nào, đừng thêm phương thức abstract nếu không có biến thể nào thực sự cần cung cấp triển khai riêng. Hợp đồng abstract tạo nghĩa vụ cho mọi lớp concrete trong hệ phân cấp liên quan, vì vậy nên đặt nó ở cấp phù hợp và dùng tên, kiểu trả về, tham số rõ ràng.

## 10. Tự kiểm tra

1. Một `abstract class` có bắt buộc khai báo ít nhất một phương thức `abstract` không? **Không.**
2. Một `class` bình thường có thể trực tiếp chứa `abstract void go();` không? **Không; lớp phải khai báo `abstract`, hoặc đổi phương thức thành có thân.**
3. Lớp con `abstract` có được trì hoãn triển khai phương thức abstract kế thừa không? **Có.**
4. Lớp con concrete có thể chỉ kế thừa triển khai hợp lệ từ lớp tổ tiên khác mà không tự viết override không? **Có, nếu nghĩa vụ đã được đáp ứng đầy đủ theo quy tắc kế thừa.**
5. Phương thức không có thân trong interface thường có mức truy cập và tính chất gì? **`public abstract` ngầm định.**
6. Có thể kết hợp `final` với khai báo lớp `abstract` không? **Không.**
7. Khi biến cha kiểu abstract gọi một phương thức abstract đã được lớp con cài đặt, mã nào chạy? **Triển khai tương ứng với đối tượng thực tế tại runtime.**

**Ghi nhớ:** Với lớp Java thông thường, *phương thức abstract buộc lớp chứa được đánh dấu abstract, nhưng lớp abstract không buộc phải có phương thức abstract*. Khi kế thừa, nghĩa vụ triển khai được chuyển tiếp cho đến khi một lớp concrete cung cấp hoặc kế thừa được triển khai hợp lệ.