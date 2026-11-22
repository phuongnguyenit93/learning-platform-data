# Phân biệt đối tượng null với phép lấy trường hoặc gọi phương thức — chẩn đoán NullPointerException

## Mục tiêu

Một ngoại lệ `NullPointerException` (NPE) không chỉ nói “ở đâu đó có `null`”. Để tìm đúng lỗi, cần xác định **tham chiếu nhận thao tác (*receiver*) nào bằng null** và **JVM đang cố đọc instance field hay gọi instance method nào** trên tham chiếu đó. Chủ đề này đặc biệt quan trọng với các biểu thức nhiều tầng, như `user.profile.city` và `user.profile().city().length()`: chỉ một dòng có thể chứa nhiều vị trí có khả năng phát sinh NPE.

Sau bài học, bạn có thể:

1. Phân biệt receiver null với field **có giá trị** null và method **trả về** null.
2. Diễn giải các dạng thông điệp `Cannot read field ...` và `Cannot invoke ...` cùng phần `because ... is null` trong Helpful NullPointerExceptions.
3. Xác định bước gây lỗi ở chuỗi truy cập nhiều tầng, không quy mọi lỗi cho object gốc hoặc field cuối.
4. Phân biệt NPE do JVM tạo khi dereference với NPE được code chủ động ném hoặc qua `Objects.requireNonNull`.
5. Sử dụng stack trace, debug từng giá trị trung gian, test ca biên và hợp đồng dữ liệu để sửa nguyên nhân chứ không chỉ bắt lỗi rồi bỏ qua.
6. Biên dịch/chạy ví dụ Java 17+ có stdout ổn định và thử quan sát thông điệp chi tiết theo môi trường thực tế.

**Phiên bản:** Cơ chế Helpful NPE (JEP 358) được đưa vào Java 14, được HotSpot bật mặc định từ Java 15, và tiếp tục được hỗ trợ trong Java hiện đại. Các ví dụ ở đây dùng **JDK 17 trở lên**, không dùng API lỗi thời hay tính năng preview.

## 1. Null không phải là đối tượng

Một biến kiểu tham chiếu có thể chứa `null`:

```java
String name = null;
```

Đoạn trên **hợp lệ**, không tự ném NPE. Điều kiện `name == null` cũng hợp lệ, và truyền giá trị null như một đối số không tự tạo NPE. NPE xuất hiện khi chương trình làm điều **cần một object thật**:

```java
String name = null;
int n = name.length(); // NullPointerException: gọi method trên null.
```

Các thao tác thường gặp có thể gây NPE là gọi instance method, đọc/ghi instance field, truy cập phần tử/độ dài mảng null, unbox wrapper null, và `throw` một reference null. Bài này tập trung vào hai hành vi đầu.

Một nguyên tắc cần giữ vững: **đọc được một giá trị null** khác với **cố đọc field hoặc gọi method trên chính giá trị null đó**.

## 2. Đọc field: receiver khác với giá trị được lưu

Giả sử có các class sau (đây là khai báo minh họa, chưa có `main`):

```java
final class Profile {
    String city;
    Profile(String city) {
        this.city = city;
    }
}

final class User {
    Profile profile;
    User(Profile profile) {
        this.profile = profile;
    }
}
```

### Trường hợp A: receiver null, chưa đọc được field

```java
User user = null;
Profile result = user.profile; // NPE.
```

Ở đây `user` là **receiver** của phép lấy field `profile`. Vì `user == null`, JVM không có instance nào để đọc field; lỗi phát sinh ngay tại phép `user.profile`. Thông điệp Helpful NPE có thể nói `Cannot read field "profile" because ... is null`.

Không được diễn giải rằng “`profile` có giá trị null”: chương trình **chưa từng đọc được field**. Object chứa field mới chính là phần thiếu.

### Trường hợp B: receiver tồn tại, field chứa null — đọc vẫn hợp lệ

```java
User user = new User(null);
Profile result = user.profile; // Hợp lệ: result == null.
```

Lần này `user` là một instance thật. JVM đọc field `profile` thành công; giá trị trả về là `null`. **Đọc một field có giá trị null không phải NPE**, miễn là object chứa field không null.

Nhưng nếu viết:

```java
User user = new User(null);
String city = user.profile.city; // NPE khi đọc city.
```

Java thực hiện hai bước:

1. Đọc `user.profile`: thành công, nhận `null`.
2. Cố đọc `city` từ kết quả của bước 1: thất bại do **receiver của phép đọc thứ hai** là null.

Khi có thông điệp chi tiết, phần thao tác có thể là `Cannot read field "city"` và nguyên nhân mô tả `user.profile` là null.

### Trường hợp C: field cuối cùng null nhưng không dùng tiếp

```java
User user = new User(new Profile(null));
String city = user.profile.city; // Hợp lệ: city == null.
```

Cả `user` và `user.profile` đều khác null nên phép lấy `city` thành công. Giá trị `city` là null. Nếu viết `city.length()` thì **lời gọi `length()` mới gây NPE**, không phải phép đọc field trước đó.

## 3. Gọi method: receiver null khác với method trả null

Bổ sung instance method sau bên trong `User`:

```java
Profile profile() {
    return profile;
}
```

### Receiver null: method chưa hề được chạy

```java
User user = null;
Profile result = user.profile(); // NPE.
```

JVM muốn gọi instance method `profile()` nhưng receiver `user` null. Method body **không được thực thi**; thông điệp có thể bắt đầu bằng `Cannot invoke "User.profile()"`.

### Method chạy bình thường và trả null

```java
User user = new User(null);
Profile result = user.profile(); // Hợp lệ: result == null.
```

Getter đã chạy, trả null theo giá trị của field. **Việc method trả null không tự động gây NPE**.

Nếu tiếp tục:

```java
User user = new User(null);
String city = user.profile().city(); // NPE ở lời gọi city().
```

Bước `user.profile()` thành công và trả null; bước `.city()` tiếp theo cố gọi trên null và thất bại. Helpful NPE có thể giải thích rằng không thể invoke `Profile.city()` vì **return value của `User.profile()` là null**.

### Một kết quả null ở cuối chuỗi

```java
User user = new User(new Profile(null));
int n = user.profile().city().length(); // NPE tại length().
```

Giả sử `Profile` có instance method `String city() { return city; }`. Khi đó `profile()` trả object hợp lệ, `city()` chạy và trả null, còn `length()` mới gây NPE. Câu `Cannot invoke "String.length()"` nói về **phép gọi đang bị chặn**, không khẳng định `city()` đã thất bại. Đó là lý do phải đọc thêm phần `because ...`.

## 4. Đọc thông điệp Helpful NPE thế nào?

Một Helpful NPE có thể nêu hai ý:

```text
Cannot <hành động không thể thực hiện> because <biểu thức nhận null> is null
```

- **Cannot read field:** JVM đang muốn đọc một instance field nhưng receiver null.
- **Cannot invoke:** JVM đang muốn gọi một instance method nhưng receiver null.
- **because ... is null:** mô tả giá trị trung gian hoặc biểu thức đã đưa null vào receiver, có thể là biến, field hay return value của method.

| Dạng minh họa | Phép toán không thực hiện được | Cách điều tra |
| --- | --- | --- |
| `Cannot read field "profile"` | Đọc `.profile` | Object trước `.profile` có null không? |
| `Cannot read field "city"` | Đọc `.city` | Kết quả trước `.city` có null không? |
| `Cannot invoke "User.profile()"` | Gọi `profile()` | Receiver của getter có null không? |
| `Cannot invoke "Profile.city()"` | Gọi `city()` | Getter trước đó có trả null không? |
| `Cannot invoke "String.length()"` | Gọi `length()` | Chuỗi đến từ field/getter có null không? |

**Thông điệp ở bảng chỉ thể hiện hình dạng, không phải văn bản chính xác được bảo đảm trên mọi JVM.** JVM dựa vào bytecode để khôi phục đường tạo ra receiver null; nó không nhất thiết giữ nguyên cách viết biểu thức nguồn. Tên class có thể đầy đủ theo package, biến có thể hiện bằng ký hiệu như `<local1>` thay cho tên gốc.

Tính năng này bổ sung thông tin, không thay thế stack trace và phân tích giá trị thực. Nếu không có Helpful NPE message, quy tắc về `null` và cách sửa lỗi **vẫn không đổi**.

## 5. Ví dụ chạy được trên Java 17+

Lưu nguyên văn tệp **`NullReceiverDiagnosticsDemo.java`**:

```java
import java.util.Objects;

public final class NullReceiverDiagnosticsDemo {
    private NullReceiverDiagnosticsDemo() {
    }

    static final class Profile {
        String city;

        Profile(String city) {
            this.city = city;
        }

        String city() {
            return city;
        }
    }

    static final class User {
        Profile profile;

        User(Profile profile) {
            this.profile = profile;
        }

        Profile profile() {
            return profile;
        }
    }

    @FunctionalInterface
    interface CheckedAction {
        void run();
    }

    static void expectNpe(String label, CheckedAction action) {
        try {
            action.run();
            throw new AssertionError("Expected NPE: " + label);
        } catch (NullPointerException expected) {
            System.out.println(label + " -> NPE");
        }
    }

    public static void main(String[] args) {
        User missingUser = null;
        User missingProfile = new User(null);
        User missingCity = new User(new Profile(null));
        User valid = new User(new Profile("Hue"));

        System.out.println("field value null = "
                + (missingProfile.profile == null));
        System.out.println("method return null = "
                + (missingProfile.profile() == null));
        System.out.println("inner field null = "
                + (missingCity.profile.city == null));

        expectNpe("read field on null user", () -> {
            Profile ignored = missingUser.profile;
        });

        expectNpe("invoke method on null user", () -> {
            Profile ignored = missingUser.profile();
        });

        expectNpe("read field on null profile", () -> {
            String ignored = missingProfile.profile.city;
        });

        expectNpe("invoke on null return value", () -> {
            String ignored = missingProfile.profile().city();
        });

        expectNpe("invoke on null city field", () -> {
            int ignored = missingCity.profile.city.length();
        });

        System.out.println("valid city = " + valid.profile().city());

        try {
            Objects.requireNonNull(missingProfile.profile,
                    "profile required");
            throw new AssertionError("Expected validation NPE");
        } catch (NullPointerException expected) {
            System.out.println("validation = "
                    + expected.getMessage());
        }
    }
}
```

Lệnh chạy bằng JDK 17 trở lên:

```bash
javac --release 17 NullReceiverDiagnosticsDemo.java
java NullReceiverDiagnosticsDemo
```

**Stdout mong đợi**, không phụ thuộc cách JVM viết nội dung chi tiết của NPE:

```text
field value null = true
method return null = true
inner field null = true
read field on null user -> NPE
invoke method on null user -> NPE
read field on null profile -> NPE
invoke on null return value -> NPE
invoke on null city field -> NPE
valid city = Hue
validation = profile required
```

**Giải thích các ca:**

1. `missingUser` là null, nên `missingUser.profile` thất bại khi **đọc field** và `missingUser.profile()` thất bại khi **gọi instance method**; getter không được chạy trong ca thứ hai.
2. `missingProfile` là object hợp lệ nhưng field `profile` null. Đọc field hoặc gọi getter độc lập đều thành công, trả null; **chỉ phép truy cập kế tiếp** đến `city` hoặc `city()` mới phát sinh NPE.
3. `missingCity.profile` là object hợp lệ với field `city` null. `missingCity.profile.city` đọc được null; `.length()` tiếp theo mới bị lỗi.
4. `valid.profile().city()` trả `"Hue"` không có exception.
5. `Objects.requireNonNull(..., "profile required")` ném NPE với **message do code chủ động cung cấp**, khác trường hợp JVM tự giải thích dereference null.
6. `expectNpe` ném `AssertionError` nếu một nhánh được cho là phải lỗi lại chạy xong; vì vậy `-> NPE` được in chỉ khi đã bắt đúng loại ngoại lệ.

Các biến `ignored` chỉ nhằm buộc Java đánh giá biểu thức và phát sinh lỗi ở đúng bước; compiler không cần sử dụng giá trị của chúng để code hợp lệ.

## 6. Quan sát chi tiết mà không phụ thuộc câu chữ

Chương trình chính chỉ in loại exception để stdout ổn định. Nếu cần đọc Helpful NPE thật, tạm thêm vào nhánh `catch (NullPointerException expected)` trong `expectNpe`:

```java
System.err.println(label + ": " + expected.getMessage());
expected.printStackTrace(System.err);
```

Đây là **hai câu lệnh minh họa cần đặt trong catch**, không phải chương trình độc lập. `getMessage()` có thể giải thích hành động bị lỗi và nguồn null; `printStackTrace()` cho biết tệp, method, dòng gây exception nếu thông tin cần thiết hiện diện.

Để cải thiện tên biến cục bộ trong thông điệp, biên dịch cùng thông tin debug:

```bash
javac --release 17 -g NullReceiverDiagnosticsDemo.java
java NullReceiverDiagnosticsDemo
```

Theo công cụ `javac`, `-g` ghi thêm thông tin debug, bao gồm tên biến cục bộ. Không có thông tin này, JVM đôi khi chỉ mô tả slot như `<local1>`. Ngoài ra, `NullPointerException.getMessage()` **có thể là null** trong những trường hợp mà JVM không còn dữ liệu cần thiết (ví dụ NPE được deserialize).

**Không viết test nghiệp vụ so sánh chính xác `getMessage().equals(...)`:** message là chi tiết phụ thuộc JVM/compiler/runtime, không phải hợp đồng ứng dụng. Thay vào đó kiểm tra **loại ngoại lệ, kết quả và invariant**; thông điệp chi tiết dùng để debug.

### Cờ JVM hiện hành

Trên HotSpot hỗ trợ Helpful NPE, có tùy chọn:

```bash
java -XX:+ShowCodeDetailsInExceptionMessages NullReceiverDiagnosticsDemo
```

Tùy chọn này **được bật mặc định từ Java 15** trong HotSpot và tiếp tục có trong JDK 17. Vì thế thông thường bạn không cần truyền cờ để chạy chương trình trên JDK 17+. Nếu môi trường tắt nó bằng `-XX:-ShowCodeDetailsInExceptionMessages`, bạn có thể không thấy nội dung chi tiết, nhưng **cùng dereference null vẫn gây NPE**.

Java 14 là phiên bản đầu tiên giới thiệu tính năng nhưng cờ chi tiết **chưa bật mặc định** khi ra mắt. Thông tin lịch sử giúp hiểu vì sao log giữa các môi trường có thể khác; ví dụ bài này chỉ dùng cách chạy JDK 17+ hiện hành, không yêu cầu quay về một phiên bản cũ.

## 7. NPE do JVM phát sinh và NPE do code tự ném

So sánh ba đoạn minh họa độc lập:

```java
String name = null;
int size = name.length(); // JVM tự ném NPE do receiver null.
```

```java
String name = null;
if (name == null) {
    throw new NullPointerException("name is required");
}
```

```java
String name = null;
java.util.Objects.requireNonNull(name, "name is required");
```

Bảng phân biệt:

| Tình huống | Nguồn lỗi | Thông điệp |
| --- | --- | --- |
| `name.length()` với name null | JVM thất bại tại `invoke` | Có thể có Helpful NPE dạng `Cannot invoke` |
| `user.profile` với user null | JVM thất bại tại `getfield` | Có thể có Helpful NPE dạng `Cannot read field` |
| `throw new NullPointerException("...")` | Code chủ động ném | Message do code truyền vào |
| `Objects.requireNonNull(x, "...")` | Kiểm tra tiền điều kiện chủ động | Message theo đối số được cung cấp |

Cả bốn đều có thể ném cùng loại `NullPointerException`, nhưng không nên suy rằng một lỗi từ `requireNonNull` nhất thiết có một field read hay method invocation bị JVM từ chối ngay tại dòng đó.

Ngược lại, nếu code **không** chủ động kiểm tra null, Helpful NPE giúp phát hiện nơi dereference xảy ra; cách sửa lâu dài thường là **không để null ngoài ý muốn truyền đến nơi đó**.

## 8. Phân tích chuỗi truy cập theo từng mắt xích

Ví dụ (mã minh họa, giả định đã có class và instance fields tương ứng):

```java
String city = order.customer.profile.address.city;
```

Tách logic thành nhiều dòng:

```java
Customer customer = order.customer;
Profile profile = customer.profile;
Address address = profile.address;
String city = address.city;
```

- Nếu `order == null`: NPE khi đọc `order.customer`.
- Nếu `order != null` nhưng `order.customer == null`: lần đọc đầu hợp lệ; NPE ở `customer.profile`.
- Nếu `profile == null`: NPE ở `profile.address`.
- Nếu `address == null`: NPE ở `address.city`.
- Nếu `address` khác null nhưng `address.city == null`: phép đọc cuối **hợp lệ** và biến `city` nhận null; NPE có thể xuất hiện ở lần dereference kế tiếp như `city.length()`.

Với chuỗi method:

```java
String upper = order.customer().city().toUpperCase();
```

Hãy xác định từng receiver và kết quả trước khi kết luận. `customer()` có thể hoàn thành thành công rồi trả null, khiến `city()` bị chặn. `city()` cũng có thể chạy thành công rồi trả null, khiến `toUpperCase()` bị chặn.

**Cẩn thận hơn:** Nếu chính **thân method** ném NPE (ví dụ khi gọi một field nội bộ), stack trace có thể chỉ vào dòng bên trong method, không phải một receiver null ở caller. Đừng xem toàn bộ NPE trên dòng có `method()` đều là lỗi gọi method trên null.

## 9. Các trường hợp và quy tắc đặc biệt

### Field null không lỗi khi chỉ đọc

```java
User u = new User(null);
Profile p = u.profile; // Hợp lệ: p nhận null.
```

### Receiver null gây lỗi khi lấy instance field

```java
User u = null;
Profile p = u.profile; // NPE ngay ở việc đọc field.
```

### Getter trả null không tự gây lỗi

```java
User u = new User(null);
Profile p = u.profile(); // Hợp lệ: getter trả null.
```

### Receiver null làm lời gọi instance method thất bại

```java
User u = null;
Profile p = u.profile(); // NPE: không thể invoke.
```

Bốn đoạn độc lập này không nên ghép nguyên xi vào một scope với nhiều biến `u` trùng tên.

**Ngoại lệ quan trọng khi mô tả “gọi trên null”:** `static field` và `static method` không phụ thuộc một instance, nên truy cập static member qua một biến có giá trị null không nhất thiết gây NPE từ chính phép truy cập static đó. Tuy nhiên, cách viết này dễ gây nhầm và không nên dùng. Hãy ưu tiên `ClassName.staticMember`. Toàn bộ phân tích về null receiver trong bài áp dụng cụ thể cho **instance fields và instance methods**.

Ngoài ra, việc gọi một constructor như `new User(null)` có thể hợp lệ hoặc bị từ chối tùy validation của class. Bản thân tham số null không phải là phép dereference.

## 10. Phòng ngừa theo hợp đồng dữ liệu

### Đầu vào bắt buộc: từ chối sớm

Nếu `name` là tham số bắt buộc:

```java
static String normalizeName(String name) {
    java.util.Objects.requireNonNull(name, "name");
    return name.strip();
}
```

Đây là **một method minh họa**, cần đặt trong một class để biên dịch. Kiểm tra ở ranh giới tạo lỗi sớm hơn, có message rõ hơn; không chờ NPE xảy ra tại một lời gọi `length()` hoặc `strip()` xa nguồn dữ liệu.

### Đầu vào được phép thiếu: xử lý có chủ đích

```java
static String cityOrUnknown(User user) {
    if (user == null || user.profile == null
            || user.profile.city == null) {
        return "UNKNOWN";
    }
    return user.profile.city;
}
```

Đoạn này giả định các class từ ví dụ ở trên. Chỉ dùng giá trị mặc định `UNKNOWN` khi contract thực sự cho phép thiếu thông tin. Nếu city là bắt buộc, âm thầm thay bằng mặc định có thể che lỗi upstream.

### Optional trong API phù hợp

Nếu một method **có thể không tìm thấy kết quả** theo thiết kế, cân nhắc trả `Optional<Profile>` và để caller xử lý vắng mặt bằng `map`/`orElse` hoặc các thao tác thích hợp. Không cần thay tất cả field và tham số bằng `Optional`. Nên quy định rõ method có trả null hay không và nhất quán qua các đường thực thi.

### Giảm chuỗi dereference dài trong luồng nghiệp vụ

Việc tách `user.profile().city()` thành biến trung gian không tự sửa null, nhưng giúp debug và validation dễ đọc. Đặt kiểm tra null ở **nơi nhận dữ liệu hoặc khởi tạo object** nếu đó là invariant; chỉ kiểm tra tại nơi sử dụng khi chính miền nghiệp vụ cho phép thiếu ở đó.

## 11. Quy trình debug thực tế

1. **Lấy stack trace**, xác định file, method và dòng Java bị lỗi.
2. **Đọc hành động** trong message nếu có: `Cannot read field` hay `Cannot invoke`? Nếu không có message chi tiết, vẫn có thể chia biểu thức nguồn.
3. **Xác định receiver của bước thất bại**, không chỉ tìm một trường có tên giống từ trong message.
4. **Theo vết nguồn null**: tham số truyền vào, field chưa khởi tạo, getter trả null, kết quả truy vấn thiếu, race condition, hoặc đường logic không xử lý dữ liệu vắng mặt.
5. **Phân biệt NPE implicit/explicit**: `Objects.requireNonNull` đã đưa ra tiền điều kiện; đừng cố đọc nó như một thông điệp bytecode cho method invocation.
6. **Tách chuỗi phức tạp** thành các biến trung gian khi cần, hoặc dùng debugger để xem từng bước.
7. **Kiểm tra phiên bản JVM và flags** nếu một môi trường có Helpful NPE, môi trường khác không; `javac -g` có thể tăng khả năng hiển thị tên biến.
8. **Viết test hồi quy** cho null ở biến gốc, null field trung gian, method trả null, null ở dữ liệu cuối cùng, và đường dữ liệu đầy đủ.
9. **Không log thông tin nhạy cảm** khi in toàn bộ object hoặc tham số, dù debugging cần chi tiết; ưu tiên đường field và thông tin không bí mật.
10. **Sửa nguyên nhân upstream** thay vì `catch (NullPointerException)` trên diện rộng rồi bỏ qua. Một NPE là dấu hiệu không thỏa contract hoặc thiếu xử lý trường hợp vắng mặt.

## 12. Bài thực hành

Tạo mô hình ba cấp `Order`, `Customer`, `Address`; `Address` có `String city`. Viết cả cách lấy field và getter.

**Phần A:**

- `Order order = null`, thử đọc `order.customer`.
- `order` khác null nhưng `customer` null, thử đọc `order.customer` rồi `order.customer.address`.
- `Customer` khác null nhưng `address` null, thử đọc `customer.address` rồi `customer.address.city`.
- `Address` khác null nhưng `city` null, thử đọc `address.city` rồi `city.length()`.
- `customer()` trả null, sau đó thử `order.customer().address()`.

Với mỗi ca, ghi **receiver null là gì, thao tác không thực hiện được là đọc field hay gọi method, và bước nào trả null bình thường trước đó**.

**Phần B:** Viết `String requireCity(Order order)`: dùng `Objects.requireNonNull` để từ chối giá trị bắt buộc ở mỗi tầng, kèm message riêng, và chỉ trả chuỗi khi đầy đủ. Viết thêm `String cityOrUnknown(Order order)` nếu business contract cho phép missing city.

**Phần C:** Chạy với `javac --release 17 -g` và bản không có `-g`, tạm in `getMessage()` và `printStackTrace()`. Quan sát thông tin tên biến (nếu có) nhưng **không** kiểm tra bằng message cố định; dùng exception type và hành vi làm test chính.

**Tiêu chí đạt:** Chỉ ra được khác biệt giữa “**lấy được null**” và “**dùng null làm receiver**”, phân tích đúng mắt xích trong chuỗi biểu thức, và đặt kiểm tra null tại nơi phù hợp với hợp đồng dữ liệu.

## Tài liệu tham khảo

- [OpenJDK JEP 358 — Helpful NullPointerExceptions](https://openjdk.org/jeps/358): thiết kế tính năng được đưa vào Java 14.
- [Oracle Java SE 17 — NullPointerException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NullPointerException.html): trường hợp phát sinh NPE và giới hạn của `getMessage()`.
- [Oracle Java SE 17 — java command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): tùy chọn `-XX:+ShowCodeDetailsInExceptionMessages`.
- [Oracle Java SE 26 — javac command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html): tùy chọn `-g`, `-g:vars`.
- [Oracle JDK 15 Release Notes](https://www.oracle.com/java/technologies/javase/15-relnote-issues.html): thời điểm Helpful NPE được bật mặc định.

**Ghi nhớ:** Một field chứa `null` vẫn có thể được đọc thành công, và một method có thể trả `null` mà không gây NPE. NPE xuất hiện khi Java cố **đọc instance field hoặc gọi instance method trên receiver null**. Helpful NPE nói rõ thao tác nào thất bại; bạn vẫn cần xem luồng tạo ra null để sửa lỗi tận gốc.