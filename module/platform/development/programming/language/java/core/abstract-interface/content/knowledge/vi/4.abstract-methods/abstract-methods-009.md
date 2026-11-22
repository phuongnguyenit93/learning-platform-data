# Phương thức package-private khi lớp con nằm khác package trong Java

Khi một lớp cha khai báo phương thức `abstract` với quyền truy cập **package-private** (không viết `public`, `protected` hay `private`), lớp con nằm **khác package** không thể triển khai/override phương thức abstract đó theo cách thông thường. Đây là điểm dễ nhầm: **phương thức cùng tên, cùng tham số, cùng kiểu trả về trong lớp con chưa chắc là một phương thức override**.

Với kiểu kế thừa xuyên package, vấn đề không chỉ là lớp con có gọi được phương thức hay không. Nó còn quyết định lớp con có thể trở thành lớp cụ thể (`concrete class`) hay phải tiếp tục là lớp `abstract`. Bài này giải thích cơ chế, trình bày các trường hợp biên dịch được và không biên dịch được, rồi chỉ ra cách thiết kế đúng.

## 1. Nhắc lại về package-private và abstract

Một phương thức trong lớp được khai báo **package-private** khi thiếu cả ba access modifier `public`, `protected`, `private`:

```java
package academy.base;

public abstract class Task {
    abstract String auditCode(); // package-private + abstract
    public abstract String execute();
}
```

- `abstract String auditCode();` không có thân hàm, yêu cầu được cung cấp triển khai phù hợp trước khi có thể tạo một đối tượng của lớp cụ thể.
- Không ghi access modifier nghĩa là **package-private**, đôi khi gọi là *default access*. Đừng nhầm với từ khóa `default` của phương thức interface.
- Quyền truy cập package-private gắn với **package khai báo lớp/phương thức**, không dựa vào việc hai lớp có tên gần giống nhau hay thuộc cùng một thư mục gốc.
- Các lớp trong **cùng package** có thể truy cập phương thức package-private (nếu thỏa các quy tắc thành viên khác). Lớp nằm **khác package** không có quyền truy cập thành viên đó theo cơ chế thông thường.
- `public abstract String execute();` được khai báo public, nên lớp con phù hợp ở package khác có thể override bằng một phương thức public.

Một phương thức abstract trong lớp có thể là `public`, `protected` hoặc package-private. Không thể kết hợp `abstract` với `private`, `final` hay `static`: chúng mâu thuẫn với yêu cầu về override của phương thức abstract.

### Override không chỉ dựa trên chữ ký

Khi xác định hai phương thức có quan hệ **overriding**, Java xét vị trí trong cây kế thừa, chữ ký, các quy tắc kiểu trả về, quyền truy cập và package. Đặc biệt, phương thức package-private trong lớp cha **không được lớp con khác package override chỉ bằng cách khai báo lại một phương thức cùng chữ ký**. Phương thức mới có thể tồn tại trong lớp con, nhưng nó không phải cách triển khai hợp lệ cho phương thức abstract package-private ban đầu.

Điều này khác với `protected`: phương thức `protected abstract` có thể được lớp con ở package khác override đúng cách, miễn đáp ứng các điều kiện còn lại.

## 2. Ví dụ lỗi: lớp con ở package khác

Xét hai tệp Java độc lập:

**`src/academy/base/Task.java`**

```java
package academy.base;

public abstract class Task {
    protected Task() {}

    abstract String auditCode(); // Chỉ package academy.base
    public abstract String execute();
}
```

**`src/academy/app/BadRemoteTask.java`**

```java
package academy.app;

import academy.base.Task;

public final class BadRemoteTask extends Task {
    public String auditCode() {
        return "attempt";
    }

    @Override
    public String execute() {
        return "remote";
    }
}
```

`Task` ở package `academy.base` và `BadRemoteTask` ở package `academy.app`. Mặc dù `BadRemoteTask.auditCode()` có cùng tên, không có tham số và cùng kiểu trả về `String`, phương thức này **không override** `Task.auditCode()`. Việc thêm `public` không thay đổi quan hệ đó. Vì thế, một `BadRemoteTask` **không phải abstract** chưa hoàn tất triển khai abstract method mà nó phải đáp ứng.

Biên dịch riêng ví dụ lỗi từ thư mục chứa `src`:

```bash
javac -encoding UTF-8 -d out src/academy/base/Task.java src/academy/app/BadRemoteTask.java
```

Kết quả: **biên dịch thất bại**. Chẩn đoán điển hình của `javac` là lớp `BadRemoteTask` không abstract và chưa override phương thức abstract `auditCode()` trong `Task`. Cách diễn đạt hoặc vị trí dòng lỗi có thể thay đổi tùy phiên bản compiler.

Nếu thêm `@Override` ngay trên `public String auditCode()` ở `BadRemoteTask`, compiler còn phát hiện trực tiếp rằng phương thức đó **không override/implement một phương thức từ supertype**. `@Override` không thể “ép” Java thay đổi quy tắc về package và visibility.

### Vì sao lớp con abstract lại khác?

Nếu khai báo `BadRemoteTask` là `abstract class`, lớp đó có thể tồn tại như một lớp trung gian chưa hoàn tất yêu cầu abstract của `Task`; vấn đề triển khai sẽ còn đó khi muốn tạo một lớp cụ thể về sau. Không thể sửa lỗi bằng cách chỉ thay `final class` thành một lớp cụ thể khác ở package ngoài trong khi giữ nguyên phương thức abstract package-private chưa được triển khai đúng.

Ví dụ rõ hơn về một khai báo **không override** (đặt trong lớp abstract ở package khác):

```java
// Trong package academy.app; chỉ là mảnh mã minh họa.
public abstract class ExternalTask extends academy.base.Task {
    public String auditCode() { // Không override Task.auditCode()
        return "another method";
    }

    @Override
    public String execute() {
        return "external";
    }
}
```

Đặt `@Override` lên `auditCode()` trong mảnh mã này sẽ tạo lỗi biên dịch. Kể cả không đặt annotation, tên phương thức trùng không có nghĩa là abstract method bên package `academy.base` đã được thực thi.

## 3. Ví dụ đúng: triển khai phương thức tại chính package của lớp cha

Có thể giữ nguyên `auditCode()` là package-private nếu thiết kế muốn phần triển khai nội bộ nằm trong `academy.base`. Tạo một lớp trung gian ở **cùng package với `Task`** để override phương thức đó, rồi cho lớp ở package khác kế thừa lớp trung gian.

Cấu trúc tệp đầy đủ:

```text
src/
└── academy/
    ├── base/
    │   ├── Task.java
    │   └── VerifiedTask.java
    └── app/
        ├── RemoteTask.java
        └── Main.java
```

**Tệp `src/academy/base/Task.java`**

```java
package academy.base;

public abstract class Task {
    protected Task() {}

    abstract String auditCode();

    public abstract String execute();

    public final String report() {
        return auditCode() + " | " + execute();
    }
}
```

**Tệp `src/academy/base/VerifiedTask.java`**

```java
package academy.base;

public abstract class VerifiedTask extends Task {
    protected VerifiedTask() {
        super();
    }

    @Override
    String auditCode() {
        return "verified";
    }
}
```

**Tệp `src/academy/app/RemoteTask.java`**

```java
package academy.app;

import academy.base.VerifiedTask;

public final class RemoteTask extends VerifiedTask {
    @Override
    public String execute() {
        return "remote";
    }
}
```

**Tệp `src/academy/app/Main.java`**

```java
package academy.app;

import academy.base.Task;

public class Main {
    public static void main(String[] args) {
        Task task = new RemoteTask();

        System.out.println(task.report());
        System.out.println(task.execute());

        // task.auditCode(); // Không biên dịch: package-private của academy.base
    }
}
```

Từ thư mục chứa `src`, biên dịch Java 17+:

```bash
javac -encoding UTF-8 -d out src/academy/base/Task.java src/academy/base/VerifiedTask.java src/academy/app/RemoteTask.java src/academy/app/Main.java
java -cp out academy.app.Main
```

**Standard output chính xác:**

```text
verified | remote
remote
```

**Phân tích:**

1. `Task.auditCode()` là package-private abstract. `VerifiedTask` được khai báo **cùng package `academy.base`** và override bằng `String auditCode()` có cùng mức truy cập. Vì vậy yêu cầu abstract `auditCode()` đã có triển khai hợp lệ.
2. `VerifiedTask` vẫn abstract vì chưa triển khai `execute()`. Lớp trung gian abstract là một lựa chọn thiết kế, không phải lỗi.
3. `RemoteTask` ở package `academy.app` kế thừa `VerifiedTask`, cung cấp `public String execute()` cho phương thức public abstract còn thiếu và trở thành lớp cụ thể.
4. Khi `Task.report()` gọi `auditCode()`, JVM chạy phần triển khai `VerifiedTask.auditCode()`. Tính đa hình qua phương thức instance đã được override vẫn hoạt động; **giới hạn truy cập ở mã nguồn không đồng nghĩa với việc JVM không thể dispatch nội bộ**.
5. Lệnh `task.auditCode()` ở `Main` vẫn không hợp lệ, do `Main` thuộc package `academy.app` và phương thức vẫn là package-private.
6. `Task task = new RemoteTask();` dùng tham chiếu kiểu cha và đối tượng thật thuộc lớp con; lời gọi `execute()` chạy phần triển khai trong `RemoteTask`.

Lưu ý rằng hai thư mục `base` và `app` được tách thành **hai package Java khác nhau** nhờ câu lệnh `package academy.base;` và `package academy.app;`. Package `academy.base.internal` cũng là package **khác** với `academy.base`; Java không cấp quyền package-private theo cấu trúc tên phân cấp.

## 4. Cách đúng nếu lớp ngoài package cần tự triển khai phương thức

Nếu yêu cầu nghiệp vụ là “mỗi lớp con bên ngoài package phải tự cài đặt `auditCode()`”, khai báo package-private abstract là thiết kế không phù hợp. Hãy dùng **`protected abstract` hoặc `public abstract`**.

### Lựa chọn A — `protected abstract`

Tệp `src/academy/base/Task.java` trong phương án thay thế:

```java
package academy.base;

public abstract class Task {
    protected Task() {}

    protected abstract String auditCode();

    public final String report() {
        return auditCode();
    }
}
```

Tệp `src/academy/app/RemoteTask.java` trong phương án thay thế:

```java
package academy.app;

import academy.base.Task;

public final class RemoteTask extends Task {
    @Override
    protected String auditCode() {
        return "remote-audit";
    }
}
```

Đây là **một phương án độc lập**, thay thế định nghĩa `Task` ở ví dụ chính; không biên dịch hai định nghĩa `Task` cùng lúc. `RemoteTask` có thể override hợp lệ vì phương thức cha là `protected`. Bên ngoài package, một lớp bất kỳ **không tự động** được phép gọi `task.auditCode()`: `protected` có quy tắc truy cập riêng cho package và subclass. Quyền override trong lớp con cũng **khác** quyền gọi qua một biến tham chiếu bất kỳ từ mã bên ngoài.

Nên dùng `protected abstract` cho **điểm mở rộng dành cho lớp con** mà không nhất thiết công khai thành API cho mọi mã khách hàng.

### Lựa chọn B — `public abstract`

Khi cả lớp con lẫn mã khách hàng cần truy cập công khai:

```java
package academy.base;

public abstract class Task {
    public abstract String auditCode();
}
```

```java
// Trong tệp khác thuộc package academy.app
package academy.app;

public final class RemoteTask extends academy.base.Task {
    @Override
    public String auditCode() {
        return "remote-audit";
    }
}
```

Hai đoạn trên đại diện **hai tệp riêng**, không ghép nhiều `package` vào một tệp Java. Khi override phương thức public, phương thức triển khai cũng phải public; không thể giảm visibility thành `protected` hoặc package-private.

`public` thích hợp khi đây là hành vi muốn đưa ra **giao diện sử dụng công khai**. Cân nhắc độ ổn định API, vì mã ngoài package có thể phụ thuộc vào phương thức.

### Lựa chọn C — Hoàn tất phần nội bộ trong cùng package

Giữ package-private abstract khi một hook là chi tiết nội bộ chỉ các lớp trong package chủ quản được phép override. Tạo lớp trung gian cùng package như `VerifiedTask` đã minh họa, sau đó cung cấp các điểm mở rộng public/protected khác cho lớp ở package ngoài.

## 5. So sánh các mức truy cập khi override xuyên package

Giả sử `Child` ở `academy.app` kế thừa `Parent` ở `academy.base`, và không có lớp trung gian đã implement phương thức abstract trước đó:

| Phương thức trong `Parent` | `Child` có thể override hợp lệ? | `Child` có thể tự hoàn tất yêu cầu abstract để trở thành concrete? |
| --- | --- | --- |
| `abstract void work();` (package-private) | **Không** qua khai báo cùng chữ ký ở package khác | **Không**; cần triển khai hợp lệ từ lớp ở cùng package cha hoặc thay đổi thiết kế |
| `protected abstract void work();` | **Có**, với visibility hợp lệ | **Có** |
| `public abstract void work();` | **Có**, bằng phương thức `public` | **Có** |
| `private void work() { ... }` | **Không**, private không được override | Không đặt ra yêu cầu abstract; `private abstract` là khai báo bất hợp lệ |
| `final void work() { ... }` | **Không**, final chặn override | Không có yêu cầu abstract do `final abstract` bất hợp lệ |

**Quy tắc chung:** lớp con override không được giảm quyền truy cập so với phương thức mà nó thực sự override. Nhưng **tăng visibility của một phương thức trùng tên ở package khác không tự tạo được quan hệ override** cho phương thức package-private inaccessible.

Trong cùng package, phương thức package-private có thể được override bằng package-private, `protected` hoặc `public`, miễn đáp ứng các quy tắc khác. Khi mở rộng visibility, phương thức mới thực sự override vì lớp con cùng package có quyền làm vậy.

## 6. Phân biệt abstract class và interface

Interface thường dùng làm hợp đồng cho nhiều lớp triển khai ở các package khác nhau. Trong Java, một phương thức **abstract của interface thông thường luôn là public** dù bạn không viết từ khóa public:

```java
package academy.base;

public interface Auditable {
    String auditCode(); // ngầm định public abstract
}
```

```java
package academy.app;

public final class RemoteAudit implements academy.base.Auditable {
    @Override
    public String auditCode() {
        return "remote-audit";
    }
}
```

Hai đoạn là hai tệp riêng, mỗi public type có tệp cùng tên. `RemoteAudit` ở package khác vẫn implement được `auditCode()` vì phương thức interface là public. Không thể implement phương thức public của interface bằng một phương thức package-private; compiler sẽ báo giảm visibility.

Không được suy luận từ cú pháp `String auditCode();` rằng nó luôn package-private: **trong class** nếu không có access modifier thì package-private, còn **trong interface** một phương thức abstract không khai báo modifier truy cập là public. Java 9+ còn cho phép private methods **có thân** trong interface để tái sử dụng logic nội bộ; chúng không phải phương thức abstract để implement từ bên ngoài.

## 7. Phân biệt “không truy cập được” với “không được thực thi”

Có ba câu hỏi độc lập:

- **Mã lớp con ở package khác có nhìn thấy/gọi được `Task.auditCode()` không?** Không, do package-private.
- **Lớp con đó có override phương thức package-private abstract trực tiếp được không?** Không; một phương thức trùng chữ ký không hoàn thành yêu cầu override.
- **Sau khi lớp cùng package implement phương thức, một phương thức public của `Task` có thể gọi implementation ấy cho đối tượng thuộc subclass package khác không?** Có, như `report()` trong ví dụ chạy được. Lời gọi xảy ra bên trong phương thức đã có quyền truy cập và dynamic dispatch tới implementation hợp lệ.

Đây là lý do không thể chỉ nói rằng “package-private không truy cập được nên JVM không chạy được phương thức”. Quy tắc về **truy cập ở mã nguồn** và **phân giải phương thức instance tại runtime** có vai trò khác nhau.

Ngoài ra, chỉ đổi kiểu của biến tham chiếu không thể mở quyền truy cập package-private:

```java
// Trong package academy.app; sử dụng các lớp ở ví dụ chạy được
academy.base.Task task = new RemoteTask();
academy.base.VerifiedTask bridge = new RemoteTask();

// task.auditCode();   // Không được phép gọi
// bridge.auditCode(); // Vẫn không được phép gọi
System.out.println(task.report()); // Hợp lệ
```

Biến tham chiếu kiểu cha hay kiểu lớp trung gian không thay đổi package của mã đang gọi. Cast xuống lớp con cũng không mở quyền truy cập phương thức package-private của package khác.

## 8. Lỗi thường gặp và cách kiểm tra

**Lỗi 1 — Cùng chữ ký nên chắc chắn override.** Với package-private và khác package, suy luận này sai. Đặt `@Override` khi dự định override để compiler xác thực. Nếu annotation báo lỗi, kiểm tra package và access modifier trước khi đoán lỗi do compiler.

**Lỗi 2 — Thêm `public` trong lớp con là đủ.** Không đủ với phương thức package-private abstract ở lớp cha khác package. Cần thay visibility **ở lớp cha** (khi bạn kiểm soát API), hoặc có một lớp trong đúng package cha triển khai trước.

**Lỗi 3 — Biến lớp con thành `abstract` rồi cho rằng đã sửa xong.** Điều này chỉ trì hoãn nghĩa vụ cung cấp implementation. Nếu muốn một lớp concrete từ nhánh đó, vẫn cần một implementation hợp lệ của abstract method còn tồn tại.

**Lỗi 4 — Nhầm package con với cùng package.** `academy.base` và `academy.base.impl` là hai package khác nhau. Không có đặc quyền package-private qua dấu chấm trong tên.

**Lỗi 5 — Quên điều kiện về constructor.** Muốn kế thừa từ package khác, lớp cha còn phải có constructor mà lớp con có thể gọi (thường là `protected` hoặc `public`). Nếu constructor không truy cập được, sẽ xuất hiện lỗi độc lập với abstract method. Các ví dụ ở trên dùng `protected Task() {}` để tách bạch hai vấn đề.

**Lỗi 6 — Nhầm class với interface.** `void run();` trong interface là `public abstract`; `abstract void run();` không có access modifier trong class là package-private. Implement interface public method bằng package-private method sẽ bị compiler từ chối.

**Lỗi 7 — Gọi package-private từ ngoài qua phương thức public trả về cùng đối tượng.** Việc có tham chiếu đến đối tượng không cấp quyền gọi thành viên inaccessible. Hãy cung cấp public method làm API hợp lệ, như `Task.report()`, nếu muốn cho phép một thao tác sử dụng phần implementation nội bộ.

### Quy trình chẩn đoán khi code không biên dịch

1. Mở khai báo abstract method **trong class hay interface**; xác định đúng visibility.
2. Xem chính xác câu lệnh `package ...;` của cả lớp cha, lớp trung gian và lớp con. Chỉ cùng chuỗi tên package mới là cùng package theo nghĩa đang xét (trong bố cục classpath/module thông thường).
3. Kiểm tra đã có lớp **cùng package với nơi khai báo phương thức** cung cấp override hợp lệ trên nhánh kế thừa hay chưa.
4. Kiểm tra `@Override` trên implementation được mong đợi, chữ ký, kiểu trả về và quyền truy cập. Nếu compiler nói không override, đừng xóa annotation như một cách che giấu vấn đề.
5. Kiểm tra lớp định tạo bằng `new` đã implement hết các abstract method còn lại chưa; lớp cụ thể không thể mang nghĩa vụ abstract chưa được đáp ứng.
6. Xem constructor của lớp cha có truy cập được từ subclass khác package không. Khi sửa visibility, chạy lại `javac` trên toàn bộ bộ tệp liên quan.

## 9. Tự kiểm tra

**Câu 1.** `package a; public abstract class Base { abstract void f(); }`. Trong `package b`, một lớp concrete `Derived extends Base` khai báo `public void f() {}`. Có compile được không?

**Đáp án:** Không. Phương thức `f()` mới bên `b` không override `Base.f()` package-private; lớp concrete vẫn chưa đáp ứng abstract method ở lớp cha.

**Câu 2.** Nếu chỉ đổi `Base.f()` thành `protected abstract void f();` và giữ `Derived.public void f() {}` thì sao?

**Đáp án:** Có thể override hợp lệ, vì `protected` cho phép subclass ở package khác override và `public` không giảm quyền truy cập. Các điều kiện khác như constructor, tên tệp, chữ ký vẫn phải đúng.

**Câu 3.** Nếu giữ `Base.f()` package-private nhưng thêm `Bridge extends Base` trong package `a` để override `f()`, rồi cho `Derived extends Bridge` ở package `b` và triển khai các abstract method còn lại?

**Đáp án:** Có thể tạo `Derived` concrete sau khi mọi abstract method đã được triển khai hợp lệ. Đây là mô hình đã chạy trong mục 3.

**Câu 4.** Trong interface `I { void f(); }`, phương thức `f()` có package-private không?

**Đáp án:** Không. Một abstract method của interface như vậy ngầm định `public abstract`; một lớp implement ở package khác được phép và phải cung cấp phương thức `public`.

**Điểm cốt lõi:** Với **abstract method package-private trong class**, *package của lớp triển khai* quyết định khả năng override. Subclass ở package khác không thể “hoàn thành” abstract method đó bằng khai báo cùng chữ ký. Muốn tạo điểm mở rộng xuyên package, dùng `protected/public abstract`; muốn giữ hook nội bộ, triển khai nó trong package của lớp cha trước khi mở rộng ra ngoài.
