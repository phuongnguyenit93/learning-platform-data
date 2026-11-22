# Dùng `this` hoặc tên lớp để chỉ rõ trường bị che khuất trong Java

## 1. Vì sao cần chỉ rõ field?

Trong constructor và method, một local/parameter có thể trùng tên field. Khi đó tên ngắn thường chọn local/parameter. Ví dụ:

~~~java
class Account {
    private int balance;
    Account(int balance) {
        this.balance = balance; // Field nhận giá trị từ tham số.
    }
}
~~~

Nếu chỉ viết `balance = balance;`, mã hợp lệ nhưng tự gán tham số, bỏ qua field. Đây là một trường hợp *shadowing*; phần giải thích các lỗi constructor/setter đã được thực hành ở bài trước. Bài này tập trung vào **các cú pháp chọn field**, đặc biệt khi có kế thừa hoặc lớp bao ngoài.

## 2. Phân biệt `this.field`, `ClassName.field` và `super.field`

| Cú pháp | Nên dùng để truy cập | Bối cảnh hợp lệ | Ý nghĩa |
| --- | --- | --- | --- |
| `field` | Biến/tham số gần nhất mang tên đó; nếu không có, có thể là field | Tùy phạm vi | Tên ngắn có thể bị che khuất |
| `this.field` | Field **instance** của đối tượng hiện tại | Constructor/phương thức/khối instance | Bỏ qua việc tên ngắn bị tham số/local che khuất |
| `ClassName.field` | Field **static** được khai báo hoặc kế thừa phù hợp trên lớp | Kể cả phương thức `static` | Chỉ rõ field thuộc lớp, không thuộc từng instance |
| `super.field` | Field instance được tìm từ lớp cha | Ngữ cảnh instance của lớp con | Phân biệt field lớp cha với field cùng tên trong lớp con |
| `object.field` | Field truy cập được qua một biến tham chiếu đối tượng | Khi có đối tượng và quyền truy cập | Chỉ rõ instance, có kiểm tra quyền truy cập |

**Lưu ý:** `ClassName.instanceField` **không hợp lệ**, vì field instance phải truy cập qua một đối tượng (`this` hoặc tham chiếu cụ thể). Ngược lại, Java cho phép một số cách truy cập field `static` qua tham chiếu đối tượng, nhưng nên sử dụng `ClassName.staticField` để tránh gây hiểu nhầm và cảnh báo từ công cụ phân tích mã.

Một trường có `private` vẫn có thể truy cập bằng `this.field` từ **bên trong chính lớp**. `this` không bỏ qua quy tắc quyền truy cập: lớp khác không thể đọc field `private` chỉ nhờ viết `someObject.field`.

## 3. Chọn đúng field instance bằng `this.field`

`this` chỉ đối tượng hiện tại của constructor/method instance. Nó cho phép chọn field ngay cả khi tên ngắn đang trỏ tới tham số hoặc local:

~~~java
class Student {
    private String name;
    Student(String name) { this.name = name; }
    String display() {
        String name = "LOCAL";
        return name + "/" + this.name;
    }
}
~~~

Với `new Student("Mai").display()`, kết quả là `LOCAL/Mai`. Trong `static` method không có `this`. Nếu không có local/parameter che khuất, dùng tên field ngắn vẫn có thể hợp lệ; `this.` giúp thể hiện rõ trạng thái instance.

## 4. Chọn đúng field `static` bằng `ClassName.field`

Với trạng thái chung của lớp, viết tên lớp trước field để tránh nhầm với local/parameter:

~~~java
class Settings {
    private static int timeout = 30;
    static void configure(int timeout) {
        Settings.timeout = timeout;
    }
}
~~~

`Settings.timeout` cập nhật field, trong khi `timeout` đơn lẻ ở vế phải là tham số. `ClassName.instanceField` không hợp lệ vì field instance cần đối tượng; truy cập field `static` qua đối tượng tuy có thể hợp lệ trong Java nhưng khiến mã khó hiểu. Kế thừa field cùng tên lại đặt ra câu hỏi khác: nên dùng `this.field` hay `super.field`?

## 5. Khi lớp con che khuất trường lớp cha: `this` và `super`

Hai lớp trong quan hệ kế thừa có thể khai báo **hai field riêng biệt cùng tên**. Đây là trường hợp *field hiding*. Không giống phương thức instance bị override, **truy cập field không sử dụng dynamic dispatch** theo kiểu runtime của đối tượng; field được chọn dựa trên kiểu tham chiếu và quy tắc tra cứu tại compile time.

```java
class Base {
    int level = 10;
}

class Derived extends Base {
    int level = 20;

    void inspect(int level) {
        System.out.println(level);       // Tham số
        System.out.println(this.level);  // Field Derived
        System.out.println(super.level); // Field Base
    }
}
```

Trong `Derived.inspect(int level)`:

- `level` là **tham số**.
- `this.level` trỏ tới field của `Derived`.
- `super.level` chọn field kế thừa từ `Base`.

Cả `Base.level` và `Derived.level` đều nằm trong cùng đối tượng `Derived`; không phải JVM tự chuyển chúng thành một trường duy nhất.

```java
Base baseView = new Derived();
Derived derivedView = (Derived) baseView;
// baseView.level == 10
// derivedView.level == 20
```

Sự khác biệt xảy ra vì kiểu biểu thức `baseView` là `Base` còn `derivedView` là `Derived`. Điều này không phải đa hình động của phương thức. `super.field` chỉ sử dụng trong ngữ cảnh instance phù hợp của lớp con và vẫn chịu giới hạn quyền truy cập của field lớp cha.

Nếu field **static** cùng tên tồn tại ở cả lớp cha và lớp con, ưu tiên viết rõ `Base.field` hoặc `Derived.field` (với quyền truy cập hợp lệ), không dựa vào tên ngắn.

## 6. Chương trình Java 17+ chạy độc lập

Tạo tệp **`FieldShadowDemo.java`**:

```java
public class FieldShadowDemo {
    private String title = "Mac dinh";
    private int level;
    private static int created = 0;

    FieldShadowDemo(String title, int level) {
        this.title = title;
        this.level = level;
        created++;
    }

    void setLevel(int level) {
        this.level = level;
    }

    void showLocalShadowing() {
        String title = "Bien cuc bo";
        System.out.println("local title: " + title);
        System.out.println("this.title: " + this.title);
    }

    static void increaseCreated(int created) {
        FieldShadowDemo.created += created;
    }

    static class Parent {
        int code = 1;
    }

    static class Child extends Parent {
        int code = 2;

        void show(int code) {
            System.out.println("parameter code: " + code);
            System.out.println("this.code: " + this.code);
            System.out.println("super.code: " + super.code);
        }
    }

    public static void main(String[] args) {
        FieldShadowDemo example = new FieldShadowDemo("Java", 1);
        System.out.println("level before: " + example.level);
        example.setLevel(4);
        System.out.println("level after: " + example.level);
        example.showLocalShadowing();

        System.out.println("created before: " + FieldShadowDemo.created);
        increaseCreated(2);
        System.out.println("created after: " + FieldShadowDemo.created);

        Child child = new Child();
        child.show(3);
        Parent asParent = child;
        System.out.println("parent view: " + asParent.code);
        System.out.println("child view: " + child.code);
    }
}
```

Tại thư mục chứa tệp, dùng JDK 17 trở lên (PowerShell, CMD, bash):

```bash
javac -encoding UTF-8 FieldShadowDemo.java
java FieldShadowDemo
```

Kết quả stdout chính xác (lệnh `javac` thành công không in gì):

```text
level before: 1
level after: 4
local title: Bien cuc bo
this.title: Java
created before: 1
created after: 3
parameter code: 3
this.code: 2
super.code: 1
parent view: 1
child view: 2
```

Giải thích:

1. Constructor và setter dùng `this.level` để tác động đúng field instance. Biến cục bộ `title` chỉ che khuất tên field trong phương thức, không xóa `this.title`.
2. Tham số `created` của phương thức `increaseCreated` không phải field `static created`. Câu lệnh `FieldShadowDemo.created += created` cập nhật field từ `1` thành `3`.
3. `Child.show` có ba cách hiểu khác nhau cho tên `code` như trong ví dụ: tham số `3`, field lớp con `2` và field lớp cha `1`.
4. `asParent.code` đọc field từ kiểu `Parent`, còn `child.code` đọc field từ kiểu `Child` mặc dù cả hai biến tham chiếu cùng một đối tượng.

## 7. Trường hợp tên trường ở lớp bao ngoài

Trong **inner class không `static`**, muốn truy cập field của đối tượng lớp bao ngoài khi tên bị che khuất, dùng `Outer.this.field`:

```java
class Outer {
    int size = 10;

    class Inner {
        int size = 20;

        void print(int size) {
            System.out.println(size);            // Tham số
            System.out.println(this.size);       // Field Inner
            System.out.println(Outer.this.size); // Field Outer
        }
    }
}
```

Đoạn này minh họa trong lớp (không phải chương trình độc lập). `Outer.this` là tham chiếu đến instance `Outer` bao quanh instance `Inner`. Nó **không áp dụng tương tự** cho lớp lồng nhau khai báo `static`, vì lớp lồng nhau static không tự mang một tham chiếu instance lớp ngoài.

## 8. Lỗi thường gặp và cách chọn cú pháp

| Lỗi/nhầm lẫn | Cách hiểu hoặc sửa |
| --- | --- |
| Constructor viết `name = name;` và tưởng field được gán | Hai tên thường cùng trỏ vào tham số; dùng `this.name = name;` |
| Trong `static` method viết `this.field` | Không có `this` trong static context; field static viết `ClassName.field`, instance cần đối tượng |
| Gọi `ClassName.instanceField` | Field instance không truy cập như field static |
| Dùng `this.field` để chọn field lớp cha khi lớp con có field trùng tên | Dùng `super.field` nếu field lớp cha có thể truy cập |
| Tưởng hai field cùng tên trong quan hệ kế thừa là một | Field hiding tạo hai field phân biệt; kiểu biểu thức quyết định field được chọn |
| Tưởng `this` vượt qua mọi giới hạn truy cập | `this` chỉ là tham chiếu hiện tại, không thay đổi quyền truy cập Java |
| Dùng `object.staticField` như field instance | Viết `ClassName.staticField` để diễn đạt rõ field thuộc lớp |

**Ghi nhớ:** dùng `this.field` để gọi rõ **field instance của đối tượng hiện tại**, dùng `ClassName.field` để gọi rõ **field static của lớp**, và dùng `super.field` khi cần **field của lớp cha** bị field lớp con che khuất. Khi tên không trùng, qualifier vẫn có thể giúp mã dễ đọc hơn, nhưng nên lựa chọn nhất quán với kiểu field.