# Trường dữ liệu, hàm tạo và phương thức trong enum

## 1. Từ một tên hằng đến một đối tượng có dữ liệu và hành vi

Một enum không chỉ là danh sách tên. Mỗi hằng enum là một đối tượng, nên có thể giữ dữ liệu riêng và dùng những phương thức được khai báo trên kiểu enum.

Ví dụ một gói sử dụng dịch vụ:

```java
enum ServicePlan {
    BASIC("basic", 100),
    PRO("pro", 1_000);

    private final String code;
    private final int requestLimit;

    ServicePlan(String code, int requestLimit) {
        this.code = code;
        this.requestLimit = requestLimit;
    }

    public String code() {
        return code;
    }

    public int requestLimit() {
        return requestLimit;
    }
}
```

Ở đây:

- `BASIC` và `PRO` là hai đối tượng thuộc tập hằng đã khai báo.
- `code` và `requestLimit` là trường của từng đối tượng.
- Các đối số sau tên hằng được dùng để chọn và gọi hàm tạo.
- Các phương thức cho phép đọc dữ liệu qua hợp đồng rõ ràng.

Không phải có một trường `requestLimit` duy nhất bị thay từ `100` sang `1_000`. `BASIC` có giá trị của nó, `PRO` có giá trị của nó.

Khi dữ liệu mô tả cố định từng giá trị của một tập hữu hạn, đặt nó trong enum giúp tránh các bảng ánh xạ hoặc nhánh điều kiện bị lặp ở nhiều nơi. Cách dùng này vẫn phù hợp trên Java hiện đại; ví dụ đầy đủ dùng Java 17+.

## 2. Bố cục thân enum

Khi enum có thành viên, phần khai báo thường theo thứ tự dễ đọc:

```text
enum TênKiểu {
    DANH_SÁCH_HẰNG(...),
    HẰNG_KHÁC(...);

    trường dữ liệu
    hàm tạo
    phương thức thể hiện
    phương thức hoặc dữ liệu static nếu cần
}
```

Đây là sơ đồ bố cục, không phải mã Java có thể biên dịch.

Điểm bắt buộc là danh sách hằng nằm trước các khai báo thành viên và kết thúc bằng dấu chấm phẩy nếu còn thành viên phía sau. Thứ tự nhóm trường, hàm tạo, phương thức sau đó là lựa chọn tổ chức mã, không phải tất cả đều bị cú pháp buộc theo đúng sơ đồ trên.

Ví dụ:

```java
enum Flag {
    OFF(false),
    ON(true);

    private final boolean enabled;

    Flag(boolean enabled) {
        this.enabled = enabled;
    }

    public boolean enabled() {
        return enabled;
    }
}
```

Dấu phẩy phân tách `OFF` với `ON`. Dấu chấm phẩy sau `ON(true)` ngăn phần hằng với trường và phương thức.

## 3. Trường thể hiện và trường static có trách nhiệm khác nhau

### 3.1. Trường thể hiện: dữ liệu của từng hằng

```java
private final String code;
private final int requestLimit;
```

Không có `static`, nên mỗi đối tượng hằng giữ một bộ dữ liệu riêng. Khi gọi:

```java
int basicLimit = ServicePlan.BASIC.requestLimit();
int proLimit = ServicePlan.PRO.requestLimit();
```

phương thức đọc trường từ đối tượng mà nó được gọi trên.

Dùng `private final` giúp biểu đạt dữ liệu được gán khi khởi tạo và không được gán lại sau đó. Đặt trường private còn cho phép API kiểm soát cách dữ liệu được công bố.

### 3.2. Trường static: dữ liệu chung của kiểu enum

Một trường `static` không có một bản riêng cho từng hằng. Nó có thể là bảng tra cứu chung hoặc thông tin chung của kiểu.

Nếu nhầm:

```java
// Thiết kế sai cho hạn mức riêng của từng gói:
// private static int requestLimit;
```

thì mọi hằng sẽ dùng chung trường đó. Ghi từ hàm tạo của từng hằng không tạo các hạn mức độc lập; với một số cách viết, Java còn chặn trực tiếp việc truy cập trường static trong hàm tạo enum vì quy tắc khởi tạo đặc biệt được giải thích ở mục 7.

Hãy quyết định theo câu hỏi: dữ liệu thuộc về **mỗi hằng** hay thuộc về **toàn bộ kiểu**?

### 3.3. final không đồng nghĩa với bất biến sâu

Một trường `final List<String>` không thể được gán lại tham chiếu sau khởi tạo, nhưng danh sách mà nó trỏ đến vẫn có thể bị sửa nếu cách cài đặt cho phép.

Vì các hằng enum được chia sẻ, thông tin mô tả cố định nên dùng dữ liệu bất biến phù hợp hoặc bản sao được kiểm soát. Với collection nhận từ bên ngoài, có thể cân nhắc bản sao không cho sửa như `List.copyOf` nếu hợp đồng cho phép và chấp nhận chính sách không có phần tử `null`.

Không lưu số yêu cầu đã dùng của từng khách hàng vào trường mutable của `ServicePlan.BASIC`. Mọi khách hàng dùng hằng `BASIC` sẽ nhìn vào cùng đối tượng enum. Số đã dùng thuộc về tài khoản hoặc phiên sử dụng; hạn mức mặc định mới là dữ liệu có thể thuộc về hằng.

## 4. Hàm tạo enum: khởi tạo tập đối tượng đã khai báo

### 4.1. Đối số của hằng đi vào hàm tạo tương ứng

```java
BASIC("basic", 100),
PRO("pro", 1_000);
```

Hai lời khai báo này cung cấp dữ liệu cho:

```java
ServicePlan(String code, int requestLimit) {
    this.code = code;
    this.requestLimit = requestLimit;
}
```

Trình biên dịch kiểm tra kiểu và số đối số. Nếu chỉ có hàm tạo hai tham số như trên, một hằng không truyền đối số phù hợp sẽ không biên dịch.

Cú pháp `BASIC(...)` không phải một phương thức factory công khai để mã bên ngoài tự tạo thêm `BASIC`. Nó là một phần khai báo hằng enum.

### 4.2. Quyền truy cập có quy tắc riêng

Hàm tạo enum không được khai báo `public` hoặc `protected`. Nếu không ghi mức truy cập, nó có quyền private theo quy tắc của enum:

```java
ServicePlan(String code, int requestLimit) {
    this.code = code;
    this.requestLimit = requestLimit;
}
```

Có thể ghi tường minh `private` nếu muốn. Dù có hàm tạo, mã ứng dụng vẫn không được viết:

```java
// Không hợp lệ:
// new ServicePlan("custom", 500);
```

Enum không cung cấp cơ chế tạo tùy ý thêm thể hiện ngoài các hằng đã khai báo.

Không gọi `super(...)` tường minh trong hàm tạo enum. Các chi tiết khởi tạo lớp cha `Enum`, gồm tên hằng và vị trí, do trình biên dịch xử lý.

### 4.3. Có thể nạp chồng và dùng this(...)

```java
enum RetryMode {
    NONE(0),
    STANDARD,
    EXTENDED(5);

    private final int attempts;

    RetryMode() {
        this(3);
    }

    RetryMode(int attempts) {
        this.attempts = attempts;
    }

    public int attempts() {
        return attempts;
    }
}
```

`STANDARD` chọn hàm tạo không tham số, rồi hàm tạo đó gọi `this(3)`. Hai hằng còn lại chọn hàm tạo nhận `int`.

Nạp chồng ở đây giúp dùng giá trị mặc định rõ ràng, không làm thay đổi giới hạn về việc tạo thêm hằng.

### 4.4. Kiểm tra dữ liệu trong hàm tạo

Có thể kiểm tra điều kiện của dữ liệu cố định:

```java
ServicePlan(String code, int requestLimit) {
    this.code = java.util.Objects.requireNonNull(code, "code");
    if (requestLimit <= 0) {
        throw new IllegalArgumentException("requestLimit must be positive");
    }
    this.requestLimit = requestLimit;
}
```

Đây là phiên bản thay thế cho hàm tạo đơn giản ở đầu bài.

Điểm cần hiểu: hàm tạo hằng chạy trong quá trình khởi tạo lớp enum, không phải khi người dùng tự gọi `new`. Nếu dữ liệu của một hằng không hợp lệ và hàm tạo ném ngoại lệ, quá trình khởi tạo kiểu có thể thất bại với `ExceptionInInitializerError`.

Vì vậy, không đưa thao tác mạng, đọc cấu hình dễ thất bại hoặc xử lý nghiệp vụ có tác dụng phụ vào hàm tạo chỉ để “tiện làm một lần”. Dữ liệu khai báo cần đơn giản, xác định và kiểm tra được.

## 5. Phương thức thể hiện: dùng dữ liệu của hằng hiện tại

Một phương thức không static có thể dùng `this` và các trường thể hiện:

```java
public boolean allows(int requested) {
    if (requested < 0) {
        throw new IllegalArgumentException("requested must be non-negative");
    }
    return requested <= requestLimit;
}
```

Cách dùng:

```java
boolean accepted = ServicePlan.PRO.allows(800);
```

Không cần truyền lại tên gói hoặc viết một bảng điều kiện để chọn hạn mức, vì phương thức đã có đối tượng `PRO` làm ngữ cảnh.

Phương thức trong ví dụ là một phép kiểm tra dựa trên hạn mức cố định. Nó không cộng dồn số lần sử dụng và không tự trừ hạn mức. API nên giữ tên và tài liệu đúng với tác động thực tế.

Các kiểu phương thức thường hữu ích:

- Đọc dữ liệu bằng `code()`, `requestLimit()`.
- Tính giá trị dẫn xuất từ dữ liệu cố định.
- Kiểm tra một điều kiện gắn với ý nghĩa của hằng.
- Cung cấp một chuỗi mô tả cho một mục đích rõ ràng.

Có thể ghi đè `toString()` nếu thật sự muốn thay biểu diễn chuỗi mặc định. `name()` vẫn là tên khai báo và không được ghi đè; mã ổn định hoặc nhãn hiển thị nên là thuộc tính được chọn rõ ràng.

Không khai báo lại các phương thức ngầm định như `values()` hoặc `valueOf(String)` với chữ ký xung đột, và không ghi đè các phương thức final của `Enum`.

## 6. Phương thức static: thao tác ở cấp kiểu enum

Một phương thức tìm theo mã thuộc về kiểu, vì trước khi tìm ta chưa chọn một hằng cụ thể:

```java
public static Optional<ServicePlan> fromCode(String code) {
    Objects.requireNonNull(code, "code");
    for (ServicePlan plan : values()) {
        if (plan.code.equals(code)) {
            return Optional.of(plan);
        }
    }
    return Optional.empty();
}
```

Đoạn này cần import `java.util.Objects` và `java.util.Optional`.

Gọi bằng:

```java
Optional<ServicePlan> plan = ServicePlan.fromCode("pro");
```

Phương thức trả một hằng đã tồn tại; nó không tạo đối tượng enum mới.

Trong hợp đồng này, mã phải khớp chính xác và mã không biết trả `Optional.empty()`. `null` bị từ chối. Cách xử lý chữ hoa–thường, khoảng trắng hay mã không hợp lệ là quyết định API, không tự được `enum` chuẩn hóa.

Cũng đừng nhầm:

- `ServicePlan.valueOf("PRO")` tìm theo **tên khai báo**.
- `ServicePlan.fromCode("pro")` trong ví dụ tìm theo **trường mã riêng**.

Phương thức static không có `this`. Nó chỉ đọc trường thể hiện khi đã có một hằng cụ thể, như biến `plan` trong vòng lặp.

## 7. Thứ tự khởi tạo và lỗi truy cập static trong hàm tạo

Các hằng enum được khởi tạo theo thứ tự khai báo, trước những trường static do người viết khai báo trong thân enum.

Vì thế, kiểu thiết kế tự đăng ký vào một map static ngay trong hàm tạo gặp vấn đề:

```java
// Ví dụ cố ý không biên dịch.
enum BadPlan {
    BASIC("basic");

    private static final java.util.Map<String, BadPlan> BY_CODE =
            new java.util.HashMap<>();

    BadPlan(String code) {
        BY_CODE.put(code, this); // Truy cập static field không phải constant variable.
    }
}
```

Dù trường map có `static final`, nó không phải biến hằng tại thời điểm biên dịch (constant variable). Khi các hằng đang được tạo, map chưa được khởi tạo ở vị trí khai báo phía dưới.

Java cấm tham chiếu trực tiếp tới trường static của chính enum từ hàm tạo, khối khởi tạo thể hiện hoặc biểu thức khởi tạo trường thể hiện, trừ trường là constant variable theo quy tắc ngôn ngữ.

Cách tổ chức phù hợp nếu cần bảng tra cứu là:

1. Hàm tạo chỉ gán dữ liệu của từng hằng.
2. Sau danh sách hằng, khởi tạo map static.
3. Trong khối static phía sau map, duyệt `values()` để điền bảng.
4. Kiểm tra mã trùng và công bố một map chỉ đọc nếu đó là hợp đồng.

Với vài hằng, phương thức duyệt tuyến tính `fromCode` ở mục 6 thường đơn giản hơn. Không cần thêm bảng tra cứu nếu lợi ích chưa đáng kể.

Tránh gọi vòng qua một helper chỉ để vượt kiểm tra truy cập trực tiếp; nó có thể đưa lỗi thứ tự khởi tạo trở lại runtime thay vì giải quyết nguyên nhân.

## 8. Chương trình hoàn chỉnh

Lưu thành `EnumMembersDemo.java`:

```java
import java.util.Objects;
import java.util.Optional;

public class EnumMembersDemo {
    public enum ServicePlan {
        BASIC("basic", 100),
        PRO("pro", 1_000),
        ENTERPRISE("enterprise", 10_000);

        private final String code;
        private final int requestLimit;

        ServicePlan(String code, int requestLimit) {
            this.code = Objects.requireNonNull(code, "code");
            if (requestLimit <= 0) {
                throw new IllegalArgumentException(
                        "requestLimit must be positive");
            }
            this.requestLimit = requestLimit;
        }

        public String code() {
            return code;
        }

        public int requestLimit() {
            return requestLimit;
        }

        public boolean allows(int requested) {
            if (requested < 0) {
                throw new IllegalArgumentException(
                        "requested must be non-negative");
            }
            return requested <= requestLimit;
        }

        public static Optional<ServicePlan> fromCode(String code) {
            Objects.requireNonNull(code, "code");
            for (ServicePlan plan : values()) {
                if (plan.code.equals(code)) {
                    return Optional.of(plan);
                }
            }
            return Optional.empty();
        }
    }

    public static void main(String[] args) {
        ServicePlan plan = ServicePlan.PRO;

        System.out.println("name = " + plan.name());
        System.out.println("code = " + plan.code());
        System.out.println("limit = " + plan.requestLimit());
        System.out.println("allows 800 = " + plan.allows(800));
        System.out.println("allows 1200 = " + plan.allows(1_200));

        ServicePlan basic =
                ServicePlan.fromCode("basic").orElseThrow();
        System.out.println("same BASIC = " + (basic == ServicePlan.BASIC));
        System.out.println("unknown = "
                + ServicePlan.fromCode("custom").isEmpty());
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all EnumMembersDemo.java
java EnumMembersDemo
```

Stdout chính xác:

```text
name = PRO
code = pro
limit = 1000
allows 800 = true
allows 1200 = false
same BASIC = true
unknown = true
```

Bốn phần của thiết kế phối hợp:

| Thành phần | Vai trò trong ví dụ |
| --- | --- |
| Đối số trên hằng | Chọn dữ liệu cố định của từng gói |
| Trường private final | Giữ dữ liệu sau khởi tạo |
| Hàm tạo | Kiểm tra và thiết lập dữ liệu |
| Phương thức thể hiện/static | Dùng dữ liệu của một hằng hoặc tìm trong tập hằng |

`fromCode` duyệt một tập nhỏ và trả về hằng có sẵn. Nếu sau này mã có thể trùng, cần quyết định hợp đồng hoặc kiểm tra tính duy nhất; hệ thống kiểu không tự chứng minh mọi chuỗi `code` khác nhau.

## 9. Những lỗi thiết kế phổ biến

### 9.1. Dùng trường static cho dữ liệu riêng của từng hằng

Hạn mức của `BASIC` và `PRO` là dữ liệu riêng, nên không static. Một bảng tra cứu tất cả gói mới là dữ liệu có thể dùng chung.

### 9.2. Viết setter cho cấu hình vốn phải cố định

Nếu cho phép `ServicePlan.PRO.setRequestLimit(...)`, mọi nơi dùng hằng `PRO` có thể thấy cấu hình bị thay đổi. Hãy đặt cấu hình thay đổi theo khách hàng ở một đối tượng riêng, thay vì sửa hằng dùng chung.

### 9.3. Coi hàm tạo như một API tạo gói tùy ý

Hàm tạo enum phục vụ tập hằng được khai báo. Khi các gói do quản trị viên tạo động, một lớp dữ liệu hoặc thực thể phù hợp hơn việc cố tìm cách `new` enum.

### 9.4. Dùng ordinal làm dữ liệu nghiệp vụ

Nếu cần mã hoặc trọng số, khai báo trường riêng. `ordinal()` là vị trí khai báo; đổi thứ tự hằng có thể đổi nó mà không phản ánh thay đổi mong muốn của nghiệp vụ.

### 9.5. Phương thức static cố truy cập trực tiếp dữ liệu thể hiện

Một phương thức static không biết hằng hiện tại là hằng nào. Nó cần nhận một hằng làm đối số, hoặc tự tìm một hằng trước khi đọc trường của đối tượng đó.

### 9.6. Dồn nghiệp vụ có trạng thái vào enum

Một phương thức thuần dựa trên dữ liệu cố định thường phù hợp. Kết nối cơ sở dữ liệu, phiên người dùng, bộ đếm dùng riêng và tài nguyên cần đóng có vòng đời khác; đưa chúng vào hằng enum dễ gây chia sẻ sai phạm vi.

## 10. Tự kiểm tra trước khi hoàn tất

Hãy đọc enum và giải thích được:

- Dữ liệu nào thuộc mỗi hằng, dữ liệu nào thuộc toàn kiểu?
- Mọi hằng có cung cấp đối số đúng với hàm tạo không?
- Hàm tạo có đơn giản và tránh phụ thuộc vào trạng thái static chưa sẵn sàng?
- Những trường được công bố có bất biến ở mức mà API hứa không?
- Phương thức thể hiện có ý nghĩa trên một hằng, còn phương thức static có ý nghĩa trên tập hằng?
- Tên khai báo, mã nghiệp vụ và nhãn hiển thị đã có trách nhiệm rõ ràng?
- Việc tìm kiếm có trả hằng có sẵn và xử lý không tìm thấy đúng hợp đồng?

Enum có trường và phương thức hữu ích khi nó gắn dữ liệu cùng hành vi ổn định với từng giá trị đã biết, đồng thời giữ trạng thái thay đổi của từng đối tượng nghiệp vụ ở ngoài các hằng dùng chung.

## Tài liệu đối chiếu

- [JLS §8.9.2 — Enum Body Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.9.2): hàm tạo, quyền truy cập và hạn chế tham chiếu static khi khởi tạo.
- [JLS §8.9.3 — Enum Members](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.9.3): thành viên do enum khai báo và những thành viên được sinh ngầm định.
- [Java Enum API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Enum.html): các phương thức nền tảng và giới hạn ghi đè.
