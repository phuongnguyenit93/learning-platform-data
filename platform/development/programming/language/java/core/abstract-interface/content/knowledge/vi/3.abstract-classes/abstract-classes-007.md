# Constructor và lựa chọn phạm vi truy cập trong lớp trừu tượng (Java)

## 1. Vì sao lớp trừu tượng vẫn có constructor?

Trong Java, một lớp khai báo `abstract` không thể được khởi tạo trực tiếp bằng `new`, nhưng **vẫn có constructor**. Constructor của lớp trừu tượng thực hiện phần khởi tạo chung của mọi đối tượng thuộc các lớp con cụ thể (concrete subclass).

Ví dụ, mọi loại công việc có thể cần một mã định danh không rỗng. Thay vì để từng lớp con lặp lại việc kiểm tra và lưu mã, lớp trừu tượng nhận mã qua constructor, kiểm tra tính hợp lệ và gán vào trường chung.

Phân biệt ba khái niệm:

- **Không thể khởi tạo lớp trừu tượng trực tiếp:** `new AbstractJob(...)` là lỗi biên dịch.
- **Constructor của lớp trừu tượng vẫn chạy:** khi `new ExportJob(...)`, constructor `AbstractJob(...)` được gọi trong chuỗi khởi tạo trước khi constructor `ExportJob(...)` hoàn tất.
- **Constructor không được kế thừa:** lớp con phải khai báo constructor của chính nó nếu cần truyền tham số cho lớp cha, và có thể gọi constructor cha bằng `super(...)`.

Constructor **không có kiểu trả về**, kể cả `void`; tên phải trùng tên lớp; không được khai báo `abstract`, `static` hay `final`. Một lớp trừu tượng có thể có nhiều constructor (constructor overloading) như lớp thông thường.

## 2. Ví dụ chạy được: `protected` constructor và lớp con khác package

Ví dụ Java 17+ dưới đây cho thấy lớp cha trừu tượng giữ dữ liệu chung, lớp con ở package khác gọi `super(jobId)`, và mã phía ngoài khởi tạo lớp con qua constructor `public`.

Cấu trúc tệp:

```text
src/
└── demo/
    ├── base/
    │   └── AbstractJob.java
    └── app/
        ├── ExportJob.java
        └── Main.java
```

**`src/demo/base/AbstractJob.java`**

```java
package demo.base;

public abstract class AbstractJob {
    private final String jobId;

    protected AbstractJob(String jobId) {
        if (jobId == null || jobId.isBlank()) {
            throw new IllegalArgumentException("jobId must not be blank");
        }
        this.jobId = jobId;
        System.out.println("AbstractJob: " + jobId);
    }

    protected final String jobId() {
        return jobId;
    }

    public abstract String execute();
}
```

**`src/demo/app/ExportJob.java`**

```java
package demo.app;

import demo.base.AbstractJob;

public final class ExportJob extends AbstractJob {
    public ExportJob(String jobId) {
        super(jobId);
        System.out.println("ExportJob ready");
    }

    @Override
    public String execute() {
        return "Export " + jobId();
    }
}
```

**`src/demo/app/Main.java`**

```java
package demo.app;

public class Main {
    public static void main(String[] args) {
        ExportJob job = new ExportJob("JOB-7");
        System.out.println(job.execute());
    }
}
```

Từ thư mục chứa `src`, biên dịch và chạy:

```bash
mkdir out
javac -d out src/demo/base/AbstractJob.java src/demo/app/ExportJob.java src/demo/app/Main.java
java -cp out demo.app.Main
```

Kết quả chính xác:

```text
AbstractJob: JOB-7
ExportJob ready
Export JOB-7
```

Giải thích:

1. `new ExportJob("JOB-7")` cấp phát một đối tượng `ExportJob`; không tạo một đối tượng `AbstractJob` riêng biệt.
2. Constructor `ExportJob(String)` gọi `super(jobId)`. Constructor `AbstractJob(String)` kiểm tra đầu vào, khởi tạo trường `private final jobId` rồi in dòng đầu tiên.
3. Sau khi constructor cha kết thúc, phần thân constructor con in `ExportJob ready`.
4. `execute()` của lớp con đọc mã qua phương thức `protected final jobId()` và in dòng cuối.

`private final` giữ trường nội bộ và chỉ cho phép gán trong giai đoạn khởi tạo hợp lệ. `protected` cho phép lớp con dùng điểm mở rộng cần thiết; `public` của `ExportJob` là giao diện khởi tạo dành cho mã sử dụng lớp con. Phương thức `execute()` là `public abstract`, nên lớp con triển khai với phạm vi `public` tương ứng.

## 3. Chọn phạm vi truy cập cho constructor của abstract class

Phạm vi truy cập áp dụng cho **lệnh gọi constructor**, độc lập với việc bản thân lớp có được khởi tạo trực tiếp hay không.

| Khai báo | Ai có thể gọi constructor? | Khi nào nên chọn? |
| --- | --- | --- |
| `public AbstractBase(...)` | Mã có quyền truy cập lớp, bao gồm các lớp con và lời gọi constructor hợp lệ | Chỉ khi muốn công khai quyền xây dựng phần base; với abstract class thường không cần rộng đến vậy |
| `protected AbstractBase(...)` | Mã cùng package; lớp con ở package khác có thể gọi thông qua `super(...)` (hoặc `this(...)` dẫn tới `super(...)`) theo quy tắc Java | Lựa chọn thường gặp khi thiết kế abstract class làm nền tảng cho lớp con ở nhiều package |
| `AbstractBase(...)` (package-private, không ghi modifier) | Các lớp trong cùng package | Giới hạn hệ phân cấp và quyền khởi tạo vào một package |
| `private AbstractBase(...)` | Bản thân lớp và các lớp cùng nest có quyền truy cập private, chẳng hạn lớp lồng bên trong phù hợp | Chủ động khóa việc tạo lớp con từ bên ngoài; chỉ các triển khai nội bộ có thể nối chuỗi constructor |

Lưu ý về `protected` ở **khác package**: quyền truy cập constructor dành cho lớp con chủ yếu được sử dụng trong khai báo constructor của lớp con thông qua `super(...)`. Nó **không** làm một lớp khác tự do gọi `new AbstractBase(...)`. Hơn nữa, `new AbstractBase(...)` đã bị cấm bởi `abstract` dù constructor là `public`.

Trước khi chọn modifier, cần phân biệt **khả năng nhìn thấy lớp** (ví dụ lớp top-level có `public` hay chỉ package-private) với **khả năng gọi constructor**. Một constructor `protected` không giúp lớp con ngoài package truy cập được một lớp cha top-level package-private.

### Vì sao `protected` thường phù hợp?

Một abstract class được thiết kế cho bên ngoài kế thừa thường có constructor `protected` để khẳng định: “Đây là thao tác khởi tạo cho các lớp con.” Constructor `public` vẫn hợp lệ, nhưng hiếm khi mang thêm lợi ích nếu người dùng cuối chỉ được tạo các lớp con cụ thể.

Nếu chỉ cho phép các lớp trong cùng package mở rộng và xây dựng đối tượng, constructor package-private có phạm vi hẹp hơn. Khi muốn kiểm soát chính xác mọi lớp triển khai bằng lớp lồng, `private` có thể phù hợp nhưng không nên chọn nếu cần subclass thông thường ở ngoài nest.

## 4. `super(...)`, `this(...)` và constructor mặc định

### 4.1. Không có constructor nào được kế thừa

Giả sử lớp trừu tượng chỉ có constructor nhận tham số:

```java
abstract class Base {
    protected Base(String name) {
        System.out.println(name);
    }
}

class Child extends Base {
    Child() {
        // Không gọi constructor cha tường minh.
    }
}
```

**Đây là ví dụ cố ý không biên dịch được.** Với Java 17, compiler tự chèn lời gọi `super()` không đối số ở đầu constructor `Child()`. Nhưng `Base` không định nghĩa constructor không đối số, nên lời gọi đó không hợp lệ.

Sửa bằng cách chuyển tham số tường minh:

```java
class Child extends Base {
    Child() {
        super("child");
    }
}
```

Đoạn sửa trên minh họa **phần khai báo lớp con**; nó dùng chung định nghĩa `Base` ngay trước đó, không phải một chương trình độc lập. Nếu cần tham số từ người tạo, lớp con có thể định nghĩa `Child(String name) { super(name); }`.

### 4.2. Khi nào Java sinh constructor mặc định?

Nếu một lớp (kể cả lớp trừu tượng) **không khai báo constructor nào**, compiler cung cấp constructor mặc định không đối số. Constructor này sẽ gọi `super()` của lớp cha; vì vậy lớp cha tiếp theo phải có constructor không đối số có thể truy cập. Nếu đã khai báo **bất kỳ constructor nào**, Java không tự thêm constructor không đối số nữa.

Hai trường hợp cần tách biệt:

- `abstract class Base {}`: có constructor mặc định, dù `new Base()` vẫn không hợp lệ.
- `abstract class Base { protected Base(int id) {} }`: chỉ có constructor đã khai báo; lớp con bắt buộc nối chuỗi đến constructor nhận `int`.

### 4.3. `this(...)` và `super(...)`

Trong một constructor Java 17, lời gọi constructor tường minh `this(...)` (constructor khác của **cùng lớp**) hoặc `super(...)` (constructor của **lớp cha**) phải là câu lệnh đầu tiên. Một constructor không được gọi trực tiếp cả hai; khi đi qua chuỗi `this(...)`, cuối cùng phải đến một lời gọi constructor cha. Không được tạo vòng lặp `this(...)`.

Ví dụ ngắn (chỉ minh họa lớp cha):

```java
abstract class Base {
    private final String name;

    protected Base() {
        this("unnamed");
    }

    protected Base(String name) {
        this.name = name;
    }

    protected final String name() {
        return name;
    }
}
```

Lớp con có thể dùng `super()` hoặc `super("custom")` nếu constructor tương ứng truy cập được. Không thể viết một lệnh như `System.out.println("start");` trước `super(...)` trong constructor khi dùng Java 17.

## 5. Thứ tự khởi tạo và bẫy gọi phương thức có thể override

Khi khởi tạo lớp con, chuỗi gọi constructor đi lên đến `Object` rồi xử lý lần lượt các lớp cha về phía lớp con. Phần khởi tạo trường và initializer của lớp cha diễn ra trước phần khởi tạo trường và initializer của lớp con; phần thân constructor cha kết thúc trước phần thân constructor con.

**Không nên gọi phương thức có thể override từ constructor lớp trừu tượng.** Java dùng dynamic dispatch: một lời gọi phương thức bị override trong constructor cha vẫn có thể chạy bản triển khai của lớp con, khi trạng thái khởi tạo riêng của lớp con chưa sẵn sàng.

Ví dụ sau độc lập và chạy được (lưu thành `Main.java`):

```java
abstract class Parent {
    protected Parent() {
        System.out.println("In parent: " + description());
    }

    protected abstract String description();
}

final class Child extends Parent {
    private String label = "ready";

    @Override
    protected String description() {
        return label;
    }
}

public class Main {
    public static void main(String[] args) {
        new Child();
    }
}
```

Chạy:

```bash
javac Main.java
java Main
```

Kết quả:

```text
In parent: null
```

`label` vẫn có giá trị mặc định `null` khi constructor `Parent` gọi `description()`; phép gán `"ready"` của lớp con xảy ra sau đó. Đây là lý do constructor cha nên kiểm tra/gán **trạng thái do chính lớp cha sở hữu**, và chỉ gọi các phương thức không thể override như phương thức `private` hoặc `final` khi phù hợp. Nếu cần hành vi phụ thuộc vào lớp con, thực hiện sau khi khởi tạo xong đối tượng.

## 6. Trường hợp `private`: chỉ các triển khai lồng bên trong

Constructor `private` của abstract class thường làm lớp con top-level không thể gọi `super(...)`. Tuy nhiên, lớp lồng cùng nest có quyền truy cập private, nên có thể dùng để giới hạn họ triển khai. Ví dụ sau là một tệp `Main.java` độc lập:

```java
abstract class Token {
    private Token() {
    }

    public static Token create() {
        return new InternalToken();
    }

    public abstract String value();

    private static final class InternalToken extends Token {
        @Override
        public String value() {
            return "internal";
        }
    }
}

public class Main {
    public static void main(String[] args) {
        Token token = Token.create();
        System.out.println(token.value());
    }
}
```

Biên dịch/chạy bằng `javac Main.java` và `java Main`, kết quả:

```text
internal
```

`Token.create()` là factory tạo lớp con nội bộ. Mã ngoài không thể `new Token()` do lớp trừu tượng, và lớp con top-level thông thường cũng không thể gọi constructor `private Token()`. Đây là kỹ thuật kiểm soát triển khai, không phải cách mặc định cho mọi abstract class.

## 7. Quy tắc chọn constructor trong thiết kế thực tế

- **Cần bảo đảm bất biến chung:** đặt tham số bắt buộc vào constructor của abstract class, kiểm tra dữ liệu ngay lúc tạo, lưu trạng thái chung vào trường `private final` khi phù hợp.
- **Cho phép mở rộng ngoài package:** thường chọn constructor `protected`; lớp con quyết định có khai báo constructor `public` cho mã sử dụng hay không.
- **Chỉ triển khai trong cùng package:** cân nhắc constructor package-private; vẫn phải xem xét phạm vi truy cập của lớp và các thành phần khác.
- **Chỉ cho phép lớp lồng triển khai:** cân nhắc `private` cùng factory tường minh; đảm bảo thiết kế thực sự cần đóng hệ phân cấp.
- **Có nhiều cách khởi tạo hợp lệ:** overload constructor và dùng `this(...)` để gom logic khởi tạo về một đường nhất quán.
- **Muốn giấu cách khởi tạo ở API công khai:** factory method có thể trả về kiểu trừu tượng; constructor của lớp con cụ thể vẫn phải nối chuỗi constructor hợp lệ.
- **Đề phòng đối tượng chưa hoàn tất khởi tạo:** tránh truy cập trạng thái subclass qua phương thức override trong constructor cha.

## 8. Lỗi thường gặp và cách chẩn đoán

| Tình huống | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `Base is abstract; cannot be instantiated` | Dùng `new Base(...)` với abstract class | Tạo lớp con cụ thể hoặc dùng factory trả về kiểu `Base` |
| `constructor Base ... cannot be applied to given types` | Compiler chèn `super()` nhưng lớp cha chỉ có constructor có tham số | Gọi `super(thamSo)` phù hợp |
| `Base(...) has private access` | Subclass không cùng nest cố gọi constructor `private` | Chọn `protected` / package-private theo phạm vi thiết kế, hoặc dùng triển khai nội bộ |
| `Base(...) has protected access` ở mã khác package | Mã sử dụng trực tiếp constructor `protected` ngoài ngữ cảnh được cho phép | Để constructor lớp con cụ thể có phạm vi phù hợp và gọi `super(...)` từ subclass |
| “call to super must be first statement” trên Java 17 | Đặt lệnh khác trước `super(...)` hoặc `this(...)` | Đưa lời gọi constructor tường minh lên đầu |
| Giá trị subclass là `null` / `0` trong constructor cha | Constructor cha gọi phương thức bị override khi subclass chưa khởi tạo trường | Bỏ lời gọi override khỏi constructor cha; hoãn hành vi đến sau khởi tạo |

Thông báo lỗi biên dịch thực tế có thể khác nhau tùy trình biên dịch và ngữ cảnh; bảng tập trung vào nguyên nhân cần kiểm tra.

## 9. Tự kiểm tra

1. Nếu `abstract class A` có constructor `protected A(int x)`, `class B extends A` ở package khác phải làm gì? → Khai báo constructor của `B` và gọi `super(x)`; Java không tự chuyển tham số cho lớp cha.
2. Vì sao `public` constructor không cho phép viết `new A(...)` khi `A` là abstract? → Quy tắc cấm khởi tạo abstract class độc lập với quyền truy cập constructor.
3. Khi nào constructor package-private phù hợp hơn `protected`? → Khi chủ đích chỉ cho phép mã trong cùng package gọi constructor, không hỗ trợ subclass ở package khác qua constructor đó.
4. Tại sao constructor lớp cha không nên gọi phương thức abstract do lớp con triển khai? → Dynamic dispatch có thể chạy mã lớp con trước khi trường lớp con được khởi tạo.
5. Nếu constructor lớp cha có tham số và không có constructor không đối số, lỗi nào có thể xảy ra ở lớp con? → `super()` ngầm định không khớp; cần `super(...)` tường minh.

**Ghi nhớ:** Constructor của abstract class là cơ chế khởi tạo phần trạng thái chung qua chuỗi constructor của lớp con. Hãy chọn modifier theo đối tượng được phép mở rộng lớp, yêu cầu bảo toàn bất biến và phạm vi API, đồng thời bảo đảm mọi đường constructor đi đến một `super(...)` hợp lệ.
