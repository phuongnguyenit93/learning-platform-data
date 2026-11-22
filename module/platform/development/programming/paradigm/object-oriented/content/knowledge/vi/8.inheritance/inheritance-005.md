# Khả năng truy cập thành viên được kế thừa trong Java

Khi một lớp **kế thừa** lớp khác bằng `extends`, lớp con có thể sử dụng những thuộc tính và phương thức được lớp cha cung cấp. Nhưng **không phải mọi thành viên của lớp cha đều được lớp con truy cập như nhau**. Quyền truy cập phụ thuộc vào modifier (`public`, `protected`, không ghi modifier hay `private`), vị trí package và đôi khi cả kiểu của biểu thức dùng để truy cập.

Đây là một điểm quan trọng của kế thừa trong OOP: **quan hệ “is-a” không đồng nghĩa với quyền nhìn thấy toàn bộ mã nội bộ của lớp cha**.

Ví dụ `PremiumAccount extends Account` nghĩa là tài khoản cao cấp cũng là một loại tài khoản, nhưng không có nghĩa `PremiumAccount` được đọc trực tiếp mã PIN `private` bên trong `Account`.

Bài học sử dụng **Java 17**. Các ví dụ về package được viết thành những tệp riêng biệt và có lệnh biên dịch để kiểm chứng.

## 1. Bảng quy tắc truy cập cần nhớ

| Modifier của thành viên lớp cha | Trong chính lớp khai báo | Lớp khác cùng package | Lớp con khác package | Code không liên quan ở package khác |
|---|---|---|---|---|
| `public` | Có | Có | Có | Có, nếu kiểu/API khả dụng |
| `protected` | Có | Có | Có, **theo giới hạn truy cập của lớp con** | Không |
| *Package-private* (không ghi modifier) | Có | Có | Không | Không |
| `private` | Có | Không\* | Không\* | Không\* |

`*` Java hiện đại cho phép một số truy cập `private` giữa các lớp **cùng nest** (ví dụ lớp lồng nhau và lớp bao), nhưng đó là ngoại lệ dựa trên *nestmate*, **không phải quyền kế thừa**. Trong trường hợp các lớp top-level thông thường ở ví dụ dưới, thành viên private không truy cập được từ lớp khác.

Một số điều kiện cần đọc cùng bảng:

- **Cùng package** nghĩa là cùng tên `package`, không phải chỉ nằm ở thư mục có tên giống nhau hoặc có cùng tiền tố (`demo.core` và `demo.core.sub` là **hai package khác nhau**).
- Một thành viên `protected` từ lớp cha **khác package** không tự nhiên trở thành public cho mọi biểu thức tham chiếu. Java còn kiểm tra truy cập qua đối tượng có kiểu phù hợp, sẽ trình bày tại phần 3.
- Bảng chủ yếu nói về **instance field và instance method**. Constructor, field static và một số quy tắc override có điểm khác.
- Quyền truy cập thành viên không khắc phục được việc **lớp chứa thành viên không truy cập được**. Ví dụ một top-level class package-private không thể được dùng từ package khác chỉ vì một method của nó khai báo public.
- Với ứng dụng Java modules (JPMS), việc package có được `exports` cho module dùng nó hay không cũng ảnh hưởng tới khả năng sử dụng public API xuyên module.

## 2. Bốn mức truy cập dưới góc nhìn kế thừa

### `public`: API được công khai

~~~java
package demo.core;

public class Document {
    public String getId() {
        return "DOC-01";
    }
}
~~~

Lớp con ở package khác hoặc code không phải lớp con có thể gọi `getId()`, miễn là chúng được phép nhìn thấy `Document`.

`public` nghĩa là phương thức thuộc giao diện công khai của lớp, nên việc sửa hành vi hoặc xóa phương thức có thể ảnh hưởng tới nhiều client. Không nhất thiết công khai field chỉ để lớp con sử dụng; thường nên ưu tiên phương thức mô tả hành vi và getter phù hợp.

### `protected`: dùng trong package và hỗ trợ lớp con

~~~java
package demo.core;

public class Account {
    protected long balance;

    protected void markUpdated() {
        System.out.println("Cập nhật");
    }
}
~~~

Code ở **cùng package `demo.core`** có thể truy cập `balance` và `markUpdated()` ngay cả khi không phải subclass.

Một subclass ở package khác có thể sử dụng hai thành viên đó trong phạm vi mà quy tắc `protected` cho phép, ví dụ `this.balance`, `super.markUpdated()`. Tuy nhiên, ngoài package, một subclass **không thể dùng protected member trên mọi đối tượng kiểu cha**; ví dụ đầy đủ ở phần kế tiếp.

### Không ghi modifier: *package-private*

~~~java
package demo.core;

public class Account {
    int retryCount;
    void resetRetryCount() {
        retryCount = 0;
    }
}
~~~

`retryCount` và `resetRetryCount()` chỉ được mã thuộc package `demo.core` truy cập. Một subclass nằm ở `demo.feature` không được quyền truy cập trực tiếp chỉ nhờ `extends Account`.

Đừng gọi mức này là `protected` hoặc “default method”: **package-private** là một kiểu quyền truy cập do không ghi access modifier, còn `default` trong interface là phương thức có sẵn implementation.

### `private`: phần cài đặt riêng của lớp khai báo

~~~java
package demo.core;

public class Account {
    private String pin = "****";

    public boolean verifyPin(String candidate) {
        return pin.equals(candidate);
    }
}
~~~

Một subclass không đọc trực tiếp được `pin`, nhưng vẫn có thể **sử dụng hành vi public/protected của lớp cha** như `verifyPin()`. Việc đóng gói chi tiết nội bộ giúp lớp cha có thể thay cách lưu trữ PIN mà lớp con không lệ thuộc vào cấu trúc dữ liệu ấy.

Không nên tạo một getter public cho mọi field private chỉ nhằm “để con nhìn thấy”. Hãy công khai khả năng mà đối tượng thực sự cần cung cấp.

## 3. Ví dụ chạy được: `protected` giữa các package

Đây là ví dụ quan trọng nhất của bài. Ta có lớp cha và một công cụ kiểm tra ở `demo.core`, một lớp con ở `demo.feature`, chương trình gọi ở `demo.app`.

Cấu trúc tệp:

~~~text
src/
└── demo/
    ├── core/
    │   ├── Document.java
    │   └── CoreInspector.java
    ├── feature/
    │   └── ManagedDocument.java
    └── app/
        └── Main.java
~~~

**Tệp `src/demo/core/Document.java`:**

~~~java
package demo.core;

import java.util.Objects;

public class Document {
    public final String id;
    protected String status;
    String internalNote;          // package-private
    private String accessToken;   // private

    public Document(String id) {
        this.id = Objects.requireNonNull(id, "id");
        this.status = "DRAFT";
        this.internalNote = "from core";
        this.accessToken = "secret-value";
    }

    protected void markReviewed() {
        status = "REVIEWED";
    }

    public String getStatus() {
        return status;
    }

    public String getMaskedToken() {
        return accessToken == null ? "" : "***";
    }
}
~~~

**Tệp `src/demo/core/CoreInspector.java`:**

~~~java
package demo.core;

public final class CoreInspector {
    public static void inspect(Document doc) {
        System.out.println(
                "core sees: " + doc.id
                + ", " + doc.status
                + ", " + doc.internalNote
        );

        // System.out.println(doc.accessToken);
        // Không hợp lệ: accessToken là private của Document.
    }
}
~~~

`CoreInspector` **không kế thừa** `Document`, nhưng vẫn đọc được `protected status` và package-private `internalNote` vì nó ở cùng package.

**Tệp `src/demo/feature/ManagedDocument.java`:**

~~~java
package demo.feature;

import demo.core.Document;

public final class ManagedDocument extends Document {
    public ManagedDocument(String id) {
        super(id); // Gọi constructor public của lớp cha.
    }

    public void review() {
        markReviewed(); // Hợp lệ: protected method được kế thừa.
        System.out.println("this.status: " + this.status);
        System.out.println("super.status: " + super.status);

        // System.out.println(internalNote);
        // Không hợp lệ: package-private ở package khác.

        // System.out.println(accessToken);
        // Không hợp lệ: private của lớp cha.
    }

    public void compare(ManagedDocument peer, Document base) {
        System.out.println("peer.status: " + peer.status);
        // Hợp lệ: peer có kiểu ManagedDocument.

        // System.out.println(base.status);
        // Lỗi biên dịch: protected member của lớp cha
        // không thể truy cập qua biểu thức kiểu Document
        // từ subclass ở package khác.
    }
}
~~~

**Tệp `src/demo/app/Main.java`:**

~~~java
package demo.app;

import demo.core.CoreInspector;
import demo.core.Document;
import demo.feature.ManagedDocument;

public class Main {
    public static void main(String[] args) {
        Document base = new Document("DOC-01");
        ManagedDocument child = new ManagedDocument("DOC-02");

        child.review();
        child.compare(new ManagedDocument("DOC-03"), base);
        CoreInspector.inspect(base);

        System.out.println("id: " + child.id);
        System.out.println("status: " + child.getStatus());
        System.out.println("token: " + child.getMaskedToken());

        // System.out.println(child.status);
        // Lỗi: Main không cùng package, không phải subclass.

        // System.out.println(child.internalNote);
        // Lỗi: internalNote chỉ thuộc phạm vi package demo.core.
    }
}
~~~

Biên dịch và chạy từ thư mục chứa `src`:

~~~bash
javac -d out src/demo/core/Document.java src/demo/core/CoreInspector.java src/demo/feature/ManagedDocument.java src/demo/app/Main.java
java -cp out demo.app.Main
~~~

Đầu ra:

~~~text
this.status: REVIEWED
super.status: REVIEWED
peer.status: DRAFT
core sees: DOC-01, DRAFT, from core
id: DOC-02
status: REVIEWED
token: ***
~~~

Ở đây cùng một field `status` có ba cách truy cập khác nhau:

- `ManagedDocument.review()` được phép dùng `this.status` và `super.status`, vì class con có quyền kế thừa protected.
- `ManagedDocument.compare(...)` được phép dùng `peer.status` vì biểu thức `peer` có kiểu `ManagedDocument`. Nhưng không được dùng `base.status` vì `base` có kiểu `Document` (lớp cha) trong ngữ cảnh package khác.
- `Main` ở package không liên quan không được đọc `child.status`, mặc dù runtime object thực tế là `ManagedDocument`. Nó có thể gọi public `child.getStatus()`.

### Tại sao quy tắc `protected` lại hạn chế kiểu biểu thức?

Java bảo vệ sự đóng gói của lớp cha. Một subclass ở package khác được phép thao tác phần protected **trong vai trò của chính nó và các đối tượng có kiểu lớp con phù hợp**, nhưng không được “mượn” đặc quyền lớp con để sửa mọi instance của lớp cha tồn tại trong hệ thống.

Theo cách diễn đạt đơn giản cho ví dụ trên: ở `ManagedDocument`, khi truy cập một protected **instance** member được khai báo trong `Document` qua biểu thức `qualifier.member`, kiểu biên dịch của qualifier phải là `ManagedDocument` hoặc kiểu con của nó. `this`, `super`, `peer` phù hợp trong cách gọi của ví dụ; `Document base` không phù hợp. Quy tắc đầy đủ cũng xét hình thức truy cập `super` và sự khác nhau giữa thành viên instance, static và constructor.

~~~mermaid
flowchart TD
    A["Member protected trong Document"] --> B{"Code truy cập ở demo.core?"}
    B -->|Có| C["Cho phép theo quyền cùng package"]
    B -->|Không| D{"Code nằm trong subclass ManagedDocument?"}
    D -->|Không| E["Không cho truy cập protected trực tiếp"]
    D -->|Có| F{"Truy cập instance qua this/super hoặc qualifier hợp lệ?"}
    F -->|Có| G["Cho phép"]
    F -->|Không| H["Lỗi biên dịch"]
~~~

Đừng coi protected là “public dành riêng cho tất cả đối tượng con”. Đây là quyền truy cập mang ngữ cảnh kế thừa, được compiler kiểm tra.

## 4. Kế thừa và khả năng truy cập là hai câu hỏi khác nhau

Hai câu hỏi dễ bị gộp thành một:

1. **Thành viên có thuộc tập thành viên được kế thừa của subclass không?**
2. **Một đoạn code cụ thể có được phép truy cập thành viên ấy không?**

Ví dụ, một field private của lớp cha vẫn **tồn tại bên trong trạng thái của đối tượng lớp con** theo mô hình đối tượng (lớp cha có phần dữ liệu riêng), nhưng Java không cho lớp con truy cập trực tiếp field đó. Nói “private bị xóa khỏi đối tượng con” là sai.

Theo quy tắc kế thừa thành viên của Java, các thành viên private của superclass **không được kế thừa** theo nghĩa thành viên có thể được lớp con sử dụng. Những phần private đó vẫn hoạt động thông qua phương thức của superclass trên một instance subclass.

Ví dụ:

~~~java
class Parent {
    private int counter;

    public void increase() {
        counter++;
    }

    public int value() {
        return counter;
    }
}

class Child extends Parent {}

class Demo {
    public static void main(String[] args) {
        Child child = new Child();
        child.increase();
        System.out.println(child.value()); // 1

        // System.out.println(child.counter); // Không hợp lệ.
    }
}
~~~

`Child` không có quyền truy cập trực tiếp `counter`, nhưng gọi được hành vi public kế thừa `increase()` và `value()`. Mã trong `Parent` vẫn quản lý field private trên đối tượng `Child`.

Với một superclass khác package, các package-private member không được sử dụng/kế thừa theo quy tắc thành viên hiện diện trong subclass ngoài package như public/protected. Đừng lẫn việc code runtime có thể gọi một implementation của superclass với khả năng class con được phép nhắc tới tên member không công khai ấy trong mã nguồn.

## 5. Lớp con có thể mở rộng quyền truy cập khi override, nhưng không được thu hẹp

Khi override một instance method, Java yêu cầu implementation lớp con không **giảm mức hiển thị** so với method mà nó override.

Ví dụ hợp lệ:

~~~java
class Parent {
    protected String label() {
        return "parent";
    }
}

class Child extends Parent {
    @Override
    public String label() { // Mở rộng protected thành public.
        return "child";
    }
}
~~~

Ví dụ không hợp lệ:

~~~java
class Parent {
    public void process() {}
}

class Child extends Parent {
    // @Override
    // protected void process() {} // Lỗi: giảm quyền public xuống protected.
}
~~~

Về mặt thiết kế, caller đã được hứa là có thể gọi một public method trên kiểu cha. Nếu một subclass được phép biến nó thành protected thì mã dùng object subclass sẽ mất quyền gọi, trái nguyên tắc thay thế.

**Chú ý thêm:**

- `protected` method có thể override thành `public` method; ngược lại không được.
- Public method phải tiếp tục public khi override.
- Method `final` không được override, bất kể mức truy cập.
- Instance method chỉ được override theo quy tắc của Java. Field **không override**; field trong subclass có thể *hide* field cùng tên của superclass.
- Method `private` của superclass không phải phương thức được subclass override. Subclass có thể khai báo phương thức cùng tên và chữ ký độc lập mà không dùng `@Override` cho phương thức private ấy.
- Package-private methods giữa các package cần được xem xét theo khả năng kế thừa/override thực tế; không thể suy ra một method cùng tên ở subclass khác package chắc chắn override method không công khai của superclass.

### Ví dụ field hiding khác method overriding

~~~java
class Parent {
    public String name = "Parent";

    public String who() {
        return "Parent";
    }
}

class Child extends Parent {
    public String name = "Child"; // Hides field Parent.name.

    @Override
    public String who() {
        return "Child";
    }
}

Parent value = new Child();

System.out.println(value.name);  // Parent
System.out.println(value.who()); // Child
~~~

Với field, Java chọn theo **kiểu tham chiếu ở lúc biên dịch**. Với instance method được override, Java chọn implementation dựa theo **kiểu object thực tế** (dynamic dispatch). Đừng dùng field hiding để thay thế đa hình của method.

## 6. Constructor được gọi khi tạo subclass, nhưng không được kế thừa

Dù lớp con có thể sử dụng nhiều member của lớp cha, **constructor không được kế thừa**.

~~~java
class Device {
    private final String serial;

    protected Device(String serial) {
        this.serial = java.util.Objects.requireNonNull(serial);
    }

    public String getSerial() {
        return serial;
    }
}

class Printer extends Device {
    public Printer(String serial) {
        super(serial); // Gọi constructor lớp cha, không kế thừa.
    }
}
~~~

Một caller ngoài package có thể tạo `new Printer("P-001")` nếu `Printer` và constructor của nó được phép truy cập; nhưng không mặc nhiên được gọi trực tiếp constructor protected của `Device` từ code ngoài package.

Trong subclass, `super(...)` phải tuân thủ các quy tắc constructor chaining của Java. Nếu constructor phù hợp của lớp cha là `private` và subclass không có quyền truy cập, compiler không thể dựng đối tượng lớp con qua constructor ấy.

Không nên thêm constructor `public` vào superclass chỉ để subclass có thể khởi tạo, nếu điều đó mở khả năng tạo superclass trực tiếp trái ý định. Một `protected` constructor thường là lựa chọn phù hợp cho abstract superclass hoặc superclass chỉ dùng thông qua lớp con.

## 7. `super` không phải “quyền truy cập đặc biệt vượt mọi giới hạn”

`super.method()` cho phép lớp con gọi một implementation được kế thừa/được phép gọi của superclass, hữu ích khi mở rộng hành vi:

~~~java
class Logger {
    protected void log(String message) {
        System.out.println("LOG: " + message);
    }
}

class TimestampLogger extends Logger {
    @Override
    protected void log(String message) {
        super.log("[EVENT] " + message);
    }
}
~~~

Lớp con có thể dùng `super.log()` vì phương thức protected được phép truy cập. Nhưng `super.privateField` không được quyền truy cập chỉ vì có từ khóa `super`, và `super` cũng không vượt qua giới hạn package-private ở package khác.

Một lớp con nên **hạn chế lệ thuộc vào field protected có thể thay đổi** nếu có thể thay bằng protected helper method hoặc public/protected API bảo vệ invariant. Field protected cho phép lớp con sửa trực tiếp dữ liệu, làm lớp cha khó thay đổi biểu diễn nội bộ.

## 8. Static member, field và nested type có quy tắc khác method động

Kế thừa không chỉ liên quan đến instance method. Một số thành viên `static` của lớp cha có thể được truy cập qua tên lớp con theo quy tắc Java; nhưng static method **không override theo đa hình runtime**, mà có thể bị *hide*.

~~~java
class Parent {
    protected static String category() {
        return "BASE";
    }
}

class Child extends Parent {
    public static String category() {
        return "CHILD";
    }
}
~~~

Ví dụ trong ngữ cảnh cùng package (hoặc phạm vi được truy cập), hai phương thức này hợp lệ nhưng không có `@Override` vì đây là static method hiding. Khi chọn phương thức static, Java dựa vào biểu thức/kiểu tại compile time theo quy tắc resolve method, khác với dynamic dispatch của instance method.

Một số nested classes và interface member cũng có thể được kế thừa hoặc dùng qua tên tương ứng, nhưng mức truy cập của kiểu lồng và lớp chứa vẫn phải được thỏa mãn.

### Interface có quy tắc truy cập khác class

Trong Java:

~~~java
interface Exportable {
    void export();
}

class PdfExport implements Exportable {
    @Override
    public void export() {
        System.out.println("Export PDF");
    }
}
~~~

Method thông thường chỉ khai báo chữ ký trong interface ngầm là **`public abstract`**. Implementation phải công khai `public`, không thể dùng package-private hoặc protected để “giấu bớt” phương thức đã được hứa công khai.

Interface không có instance fields; mọi field trong interface ngầm là `public static final`. Vì vậy đừng đem nguyên cách suy luận về field `protected` hoặc `private` của superclass sang interface.

## 9. Không lạm dụng `protected`: chọn điểm mở rộng đúng

Một protected field tiện cho subclass nhưng cũng làm subclass phụ thuộc vào cấu trúc dữ liệu lớp cha:

~~~java
class Account {
    protected long balance;
}
~~~

Giả sử sau này lớp cha muốn chuyển từ `long` sang một value object `Money`. Mọi lớp con đang đọc/sửa `balance` trực tiếp có thể phải thay đổi.

Một phương án kiểm soát tốt hơn là giữ field private và đưa ra hành vi có quy tắc:

~~~java
class Account {
    private long balance;

    protected final long currentBalance() {
        return balance;
    }

    protected final void credit(long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Số tiền phải dương");
        }
        balance = Math.addExact(balance, amount);
    }
}

class RewardAccount extends Account {
    public void receiveReward(long points) {
        credit(points);
    }

    public long availableBalance() {
        return currentBalance();
    }
}
~~~

`balance` private, nên subclass không tùy ý gán trực tiếp số âm. Hai protected methods thể hiện những thao tác mà lớp cha cho phép subclass thực hiện, đồng thời có thể kiểm soát invariant.

**Nhưng** `protected final credit(...)` cũng là một lời hứa API dành cho lớp con. Đừng tạo quá nhiều protected hooks khi không có nhu cầu mở rộng thực tế, vì chúng tạo thêm trách nhiệm giữ tương thích về sau.

Nếu subclass thường phải chạm sâu vào nhiều chi tiết nội bộ để hoạt động, hãy xem xét **composition**: đưa phần thay đổi hành vi ra một collaborator hoặc strategy, để giảm sự gắn kết giữa các thế hệ lớp.

## 10. Hệ quả của package và module khi phát hành thư viện

Khi tổ chức source code, package là ranh giới quyền truy cập quan trọng:

~~~text
com.example.core            // package A
com.example.core.internal   // package B khác A
com.example.plugin          // package C
~~~

Mặc dù có cùng tiền tố `com.example.core`, package `com.example.core.internal` **không được** truy cập thành viên package-private của `com.example.core`.

Nếu dùng Java Platform Module System (JPMS), thư viện còn có thể đóng package khỏi những module khác:

~~~java
module com.example.library {
    exports com.example.api;
}
~~~

Module khác có thể dùng public API trong package được `exports` nếu đáp ứng các điều kiện module liên quan. Public class trong package **không được export** không tự động trở thành public API sử dụng được từ module ngoài.

Điều này khác với modifier `protected` ở cấp member: quyền truy cập thành viên chỉ phát huy khi lớp/package chứa thành viên đã accessible trong ngữ cảnh của chương trình.

Không nên coi reflection hoặc `setAccessible(true)` là một quyền tự động vượt qua giới hạn `private`. Cơ chế reflection chịu kiểm tra quyền và ràng buộc mạnh của module; đồng thời việc phụ thuộc vào chi tiết không công khai làm mã dễ vỡ.

## 11. Bảng lỗi thường gặp khi làm việc với thành viên kế thừa

| Lỗi | Nguyên nhân | Cách suy nghĩ đúng |
|---|---|---|
| Subclass khác package gọi trực tiếp field package-private của cha | Package-private chỉ cho cùng package | Chuyển sang API `protected`/`public` cần thiết hoặc thay thiết kế |
| Subclass đọc `base.protectedField` với biến `Base base` từ package khác | Có thêm quy tắc kiểu qualifier trong protected access | Dùng `this`, `super`, tham chiếu kiểu subclass thích hợp hoặc public API |
| Code ngoài package gọi `child.protectedMethod()` | Không phải subclass, không cùng package | Cung cấp public hành vi thực sự cần |
| Gọi `super.privateMethod()` | Private của superclass không được kế thừa/truy cập kiểu này | Dùng hành vi public/protected do cha chủ động cung cấp |
| Override `public` method thành `protected` | Giảm visibility so với method cha | Giữ public hoặc thiết kế API khác |
| Thêm `@Override` cho method trùng tên private superclass | Private method không bị override | Hiểu đây là khai báo riêng trong subclass |
| Nhầm constructor superclass được kế thừa | Constructor không phải member được kế thừa | Dùng `super(...)` để khởi tạo phần superclass |
| Dùng protected field để subclass ghi tùy ý | Dễ phá invariant | Ưu tiên protected method có validation hoặc composition |
| Coi `subpackage` là cùng package | Package Java xác định bằng tên đầy đủ | Tách đúng ranh giới module/package |
| Cho rằng `public` vượt mọi ranh giới JPMS | Package/class còn phải accessible từ module dùng | Thiết kế public API và `exports` thích hợp |

## 12. Luyện tập

### Bài 1: dự đoán kết quả

~~~java
class Parent {
    private int value = 7;

    public int getValue() {
        return value;
    }
}

class Child extends Parent {}

Child child = new Child();
System.out.println(child.getValue());
~~~

**Đáp án:** in `7`. Field `value` là private, nhưng phương thức `getValue()` public được kế thừa, và mã của `Parent` đọc được field private của chính nó trên object `Child`.

### Bài 2: hai package

~~~java
// package alpha;
public class A {
    protected int number = 9;
}

// package beta;
public class B extends A {
    void print(A a, B b) {
        System.out.println(this.number);
        System.out.println(b.number);
        // System.out.println(a.number);
    }
}
~~~

Giả sử hai class được đặt trong các tệp/package hợp lệ. Dòng nào trong `print` sẽ không biên dịch nếu bỏ comment?

**Đáp án:** `a.number`. Bên trong `B` ở package khác, không được truy cập protected instance member từ biểu thức có kiểu `A` như vậy. `this.number` và `b.number` hợp lệ.

### Bài 3: override có thể tăng quyền không?

~~~java
class A {
    protected void run() {}
}

class B extends A {
    @Override
    public void run() {}
}
~~~

**Đáp án:** hợp lệ. `B.run()` tăng quyền từ protected lên public. Nếu đổi ngược public ở cha thành protected ở con thì không hợp lệ.

### Bài 4: constructor

~~~java
class Parent {
    protected Parent(int n) {}
}

class Child extends Parent {
    Child() {
        super(10);
    }
}
~~~

**Đáp án:** subclass `Child` có thể gọi constructor protected của superclass bằng `super(10)` theo quy tắc constructor invocation. Nó **không thừa hưởng** constructor `Parent(int)` như một constructor tên `Child(int)`.

### Bài 5: bảo vệ invariant

Một lớp cha có `protected int stock`; subclass có thể viết `stock = -50`. Bạn nên sửa thiết kế ra sao?

**Gợi ý:** đưa field thành private, cung cấp các phương thức `protected` hoặc public mang ý định như `receive(quantity)`, `reserve(quantity)`, `ship(quantity)` có validation. Lớp con chỉ thao tác qua hành vi được phép, tránh phá invariant.

### Bài 6: field hiding

~~~java
class P {
    public int number = 1;
}

class C extends P {
    public int number = 2;
}

P ref = new C();
System.out.println(ref.number);
~~~

**Đáp án:** in `1`. Field được chọn theo kiểu biên dịch `P` của `ref`. Không nên dùng field hiding làm cơ chế đa hình.

## 13. Quy trình xác định một truy cập có hợp lệ hay không

Khi đọc một biểu thức như `obj.someMember` hoặc `super.someMethod()`, hãy hỏi theo thứ tự:

1. **Thành viên được khai báo ở đâu?** Xác định superclass, member, modifier, và nó có bị hide/override không.
2. **Code hiện tại thuộc package và class nào?** Trùng package cho phép package-private và protected; subclass ở package khác có quy tắc riêng.
3. **Biểu thức nhận lời gọi có kiểu gì tại compile time?** Đặc biệt quan trọng đối với protected instance member từ superclass khác package.
4. **Thành viên là field, instance method, static method hay constructor?** Override và method dispatch chỉ áp dụng theo từng loại.
5. **Kiểu và module có accessible không?** Với JPMS hoặc package-private top-level class, member `public` chưa đủ để truy cập.
6. **Truy cập đó có đúng về thiết kế không?** Có thể biên dịch không đồng nghĩa nên mở field cho subclass sửa trực tiếp.

**Ghi nhớ:** kế thừa giúp lớp con sử dụng và mở rộng hành vi của lớp cha, nhưng `public`, `protected`, package-private và `private` xác định ranh giới truy cập. Trong Java, `protected` có quy tắc đặc biệt khi subclass nằm ngoài package; `private` không được kế thừa như một API truy cập được; constructor không được kế thừa. Thiết kế lớp cha với các phương thức có ý nghĩa và quyền truy cập vừa đủ sẽ giúp hệ kế thừa dễ dùng và ít phụ thuộc chi tiết nội bộ hơn.