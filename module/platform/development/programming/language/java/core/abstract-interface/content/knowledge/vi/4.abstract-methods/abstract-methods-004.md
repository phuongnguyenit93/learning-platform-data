# Phạm vi `public`, `protected` và package-private của phương thức abstract trong Java

Access modifier quyết định mã nào có thể gọi một phương thức và lớp con nào có thể override nó. Với phương thức `abstract` trong một class, Java cho phép `public`, `protected` hoặc package-private (không ghi modifier). Ba lựa chọn này tạo ra các hợp đồng có phạm vi khác nhau.

## 1. So sánh ba mức truy cập

```java
public abstract class Task {
    public abstract String title();
    protected abstract int priority();
    abstract String internalCode();
}
```

| Khai báo trong class | Mã cùng package gọi được? | Lớp con ở package khác có thể override? | Mã thông thường ở package khác gọi trực tiếp? |
|---|---|---|---|
| `public abstract` | Có | Có; override phải `public` | Có, nếu kiểu chứa truy cập được |
| `protected abstract` | Có | Có; override phải `protected` hoặc `public` | Không tùy ý; phải thỏa quy tắc `protected` |
| package-private `abstract` | Có | Không bằng cách khai báo cùng chữ ký ở package khác | Không |

Package-private đôi khi được gọi là *default access*. Đây không phải từ khóa `default` dùng để khai báo phương thức có thân trong interface. Quyền package-private dựa trên package Java được khai báo trong source, không dựa vào việc hai package có tên gần nhau hoặc nằm trong cùng thư mục cha.

## 2. Quy tắc visibility khi override

Lớp con được giữ nguyên hoặc mở rộng mức truy cập của phương thức mà nó thật sự override; không được thu hẹp:

| Modifier ở lớp cha | Modifier override hợp lệ |
|---|---|
| `public` | `public` |
| `protected` | `protected`, `public` |
| package-private | package-private, `protected`, `public` nếu lớp con thật sự cùng package và nhìn thấy phương thức |

Ví dụ sai:

```java
abstract class Job {
    public abstract void run();
}

class BadJob extends Job {
    @Override
    protected void run() { // Lỗi: giảm public thành protected
        System.out.println("run");
    }
}
```

Sửa thành `public void run()`. Dùng `@Override` để compiler kiểm tra rằng chữ ký thực sự override một phương thức kế thừa. Đổi visibility không thể biến một phương thức không nhìn thấy thành override hợp lệ.

## 3. Ví dụ chạy được: gọi API công khai, giữ hook nội bộ

Các tệp dưới đây nằm trong cùng package `academy.tasks`, ngoại trừ `Main` ở package `app`.

**`src/academy/tasks/Task.java`**

```java
package academy.tasks;

public abstract class Task {
    public abstract String title();
    protected abstract int points();
    abstract String code();

    public final String summary() {
        return title() + " | " + points() + " | " + code();
    }
}
```

**`src/academy/tasks/ReviewTask.java`**

```java
package academy.tasks;

public final class ReviewTask extends Task {
    @Override
    public String title() {
        return "Review";
    }

    @Override
    protected int points() {
        return 3;
    }

    @Override
    String code() {
        return "REV-01";
    }
}
```

**`src/app/Main.java`**

```java
package app;

import academy.tasks.ReviewTask;
import academy.tasks.Task;

public class Main {
    public static void main(String[] args) {
        Task task = new ReviewTask();
        System.out.println(task.title());
        System.out.println(task.summary());
    }
}
```

Biên dịch từ thư mục chứa `src`:

```bash
javac -encoding UTF-8 -d out src/academy/tasks/Task.java src/academy/tasks/ReviewTask.java src/app/Main.java
java -cp out app.Main
```

Kết quả:

```text
Review
Review | 3 | REV-01
```

`Main` gọi được `title()` và `summary()` vì chúng là public. `points()` là protected, còn `code()` là package-private; mã trong `app` không được gọi trực tiếp hai phương thức này. Tuy vậy, `summary()` có thể gọi chúng bên trong `Task`, nơi access hợp lệ, và dynamic dispatch chọn implementation ở `ReviewTask`. Giới hạn truy cập ở mã nguồn không ngăn lời gọi nội bộ hợp lệ đến implementation.

## 4. Khi lớp con nằm ở package khác

Subclass ở package khác có thể override `protected abstract` hoặc `public abstract` nếu tuân thủ chữ ký và visibility. Với phương thức package-private abstract, khai báo một phương thức cùng tên và tham số ở package khác **không** đáp ứng hợp đồng của lớp cha; một lớp con concrete trực tiếp vẫn còn phương thức abstract chưa được triển khai.

Nếu lớp ngoài package phải tự cung cấp implementation, hãy thiết kế hook là `protected abstract` hoặc `public abstract`. Nếu hook phải được giữ nội bộ trong package của lớp cha, có thể để một lớp cùng package triển khai nó trước khi mở rộng hệ phân cấp ra ngoài. Bài chuyên về package-private xuyên package trình bày trường hợp này và cách triển khai lớp trung gian chi tiết hơn.

## 5. Khác biệt của interface

Phương thức abstract thông thường trong interface mặc định là `public abstract`, không phải package-private:

```java
public interface Action {
    void execute(); // public abstract ngầm định
}

final class PrintAction implements Action {
    @Override
    public void execute() {
        System.out.println("done");
    }
}
```

Lớp triển khai bắt buộc giữ `public`; viết `protected` hoặc package-private sẽ giảm visibility và bị compiler từ chối. Interface có thể có phương thức `default`, `static` hoặc `private` **có thân**, nhưng những dạng này không tạo ra một abstract method package-private.

## 6. Chọn modifier theo mục đích

- Dùng `public abstract` khi hành vi là một phần của API mà mã khách hàng cần gọi.
- Dùng `protected abstract` khi muốn cho lớp con mở rộng hành vi nhưng không công khai lời gọi cho mọi caller.
- Dùng package-private abstract khi implementation được kiểm soát trong cùng package và không cần subclass bên ngoài tự hoàn thành hook.
- Trước khi đổi visibility để chữa lỗi compiler, hãy xác định ai cần gọi phương thức và package của lớp triển khai. `protected` cho phép override xuyên package nhưng không biến phương thức thành API công khai cho mọi đối tượng.

## 7. Lỗi thường gặp và tự kiểm tra

| Triệu chứng | Nguyên nhân cần kiểm tra |
|---|---|
| `attempting to assign weaker access privileges` | Override dùng visibility hẹp hơn hợp đồng gốc |
| `does not override abstract method` | Chữ ký sai, chưa triển khai đủ, hoặc phương thức package-private nằm ở package khác |
| Không gọi được `protected` từ mã ngoài | Caller không thỏa quy tắc truy cập `protected` |
| Implement interface báo visibility yếu hơn | Quên rằng abstract method trong interface là public |

1. `abstract void save();` trong class thuộc mức nào? **Package-private.**
2. Lớp con khác package có thể override `protected abstract void save();` bằng `public void save()` không? **Có.**
3. `void save();` trong interface có package-private không? **Không, nó ngầm định public abstract.**
4. Lớp con khác package khai báo cùng chữ ký với một package-private abstract method đã hoàn thành hợp đồng chưa? **Chưa; đó không phải override hợp lệ.**
