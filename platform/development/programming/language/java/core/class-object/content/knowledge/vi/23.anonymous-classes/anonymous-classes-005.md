# Ý nghĩa `this` và truy cập đối tượng bao ngoài trong lớp vô danh Java

## 1. Câu hỏi trung tâm

Trong Java, khi một **lớp vô danh (*anonymous class*)** được khai báo trong một method của lớp `Outer`, từ khóa `this` trong **thân lớp vô danh** trỏ đến đối tượng nào?

**Trả lời:** `this` bên trong instance method hoặc initializer của lớp vô danh trỏ đến **chính đối tượng vô danh đang thực thi**, không phải đối tượng `Outer` đã tạo nó. Nếu lớp vô danh được tạo tại một **instance context** có enclosing instance `Outer` phù hợp, dùng **`Outer.this`** để chỉ rõ đối tượng `Outer` ấy.

```java
class Outer {
    String title = "OUTER";

    Runnable create() {
        return new Runnable() {
            String title = "ANONYMOUS";

            @Override
            public void run() {
                System.out.println(this.title);
                System.out.println(Outer.this.title);
            }
        };
    }
}
```

Đây là **khai báo class minh họa hợp lệ**, chưa có `main`. Trong method `run`:

- `this.title` là field của **anonymous Runnable object**.
- `Outer.this.title` là field của **enclosing Outer object**.
- `title` không có định danh sẽ được giải quyết theo quy tắc phạm vi, có thể chỉ field anonymous khi không có tên gần hơn.
- `Outer.this` không tạo mới một Outer instance và không chọn một Outer bất kỳ trong chương trình.

Bài viết này phân biệt ba trường hợp hay nhầm: **lớp vô danh**, **lớp bao ngoài** và **lambda**, đồng thời kiểm chứng bằng Java 17+ với tên file, lệnh chạy và stdout xác định.

## 2. Nhận diện một lớp vô danh

Lớp vô danh được khai báo cùng biểu thức tạo đối tượng, chẳng hạn:

```java
Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println("working");
    }
};
```

Đây là **mảnh code** trong method hợp lệ.

- `new Runnable() { ... }` tạo một instance của một **anonymous class implementing Runnable**.
- Lớp này không có tên source-level riêng để gọi `new SomeAnonymousClass()` ở chỗ khác.
- Nó có thể override methods, khai báo fields, instance initializers và methods hỗ trợ (theo các quy tắc Java áp dụng).
- Không thể khai báo **constructor có tên** cho anonymous class vì nó không có source-level class name.
- Có thể dùng `this` trong instance context của thân anonymous class để thao tác với chính object đang được tạo/chạy.
- Nó có thể được trả ra qua `Runnable`, `Comparator`, superclass hoặc interface mà caller nhìn thấy.

**Một anonymous class khác lambda:** Cả hai có thể cung cấp một `Runnable`, nhưng **ý nghĩa `this` khác hẳn**. Trong anonymous class, `this` là anonymous object; trong lambda, `this` theo lexical enclosing context.

## 3. Ví dụ chạy đầu tiên: `this` của anonymous và `Outer.this`

Tạo tệp **`AnonymousThisBasicsDemo.java`**:

```java
class Outer {
    private final String title;

    Outer(String title) {
        this.title = title;
    }

    Runnable task() {
        return new Runnable() {
            private final String title = "ANONYMOUS";

            @Override
            public void run() {
                System.out.println("this=" + this.title);
                System.out.println("outer=" + Outer.this.title);
            }
        };
    }
}

public class AnonymousThisBasicsDemo {
    public static void main(String[] args) {
        Outer outer = new Outer("OWNER");
        Runnable task = outer.task();
        task.run();
    }
}
```

Chạy với JDK 17+:

```bash
javac AnonymousThisBasicsDemo.java
java AnonymousThisBasicsDemo
```

**Standard output:**

```text
this=ANONYMOUS
outer=OWNER
```

### Giải thích theo object identity

1. `new Outer("OWNER")` tạo Outer object A.
2. `outer.task()` gọi instance method trên object A.
3. Trong `task()`, `new Runnable() { ... }` tạo anonymous Runnable object B, có runtime identity riêng.
4. Khi `B.run()` thực thi, `this` trỏ **B**.
5. Từ vị trí mã khai báo anonymous class, có enclosing Outer instance A, nên `Outer.this` trỏ **A**.

Sơ đồ logic:

```text
outer ---------> Outer A { title = "OWNER" }
                     ^
                     | enclosing instance
                     |
task ----------> Anonymous Runnable B
                  { title = "ANONYMOUS" }

Trong B.run():
    this       == B
    Outer.this == A
```

Không cần biết JVM đặt instances ở địa chỉ bộ nhớ nào, hay compiler sinh field tổng hợp tên gì. Java quy định **ý nghĩa biểu thức**, không yêu cầu application code dựa vào layout thực thi.

## 4. `this` thực sự là một reference đến anonymous object

`this` không chỉ dùng để truy cập field. Trong anonymous class, bạn có thể dùng nó để:

- So sánh identity: `this == anotherReference` nếu types cho phép.
- Gọi instance method của anonymous object: `this.describe()`.
- Trả object dưới một supertype, ví dụ `Runnable`.
- Truyền object vào một helper method nhận interface/superclass phù hợp.
- Dùng method reference có receiver: `this::run` trong trường hợp target functional interface phù hợp.

Tạo **`AnonymousIdentityDemo.java`**:

```java
class Outer {
    Runnable create() {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println(this instanceof Runnable);
                System.out.println(this == (Object) Outer.this);
                System.out.println(getClass().isAnonymousClass());
            }
        };
    }
}

public class AnonymousIdentityDemo {
    public static void main(String[] args) {
        Runnable task = new Outer().create();
        task.run();
    }
}
```

```bash
javac AnonymousIdentityDemo.java
java AnonymousIdentityDemo
```

```text
true
false
true
```

- `this instanceof Runnable` đúng vì anonymous class implements Runnable.
- `this == (Object) Outer.this` là false: anonymous object và enclosing Outer object là hai instances khác nhau. Ép Outer reference về Object ở đây để so sánh references theo identity mà không vướng quy tắc compile-time về hai types không liên quan.
- `getClass().isAnonymousClass()` xác nhận runtime class của receiver là anonymous class, không phụ thuộc tên class do compiler sinh.

**Không kiểm `getClass().getName()` theo một chuỗi hardcode** vì tên nhị phân của anonymous class là chi tiết compiler/runtime, không phải API nguồn ổn định.

## 5. Field trùng tên: `name`, `this.name`, `Outer.this.name`

Đây là tình huống shadowing phổ biến nhất. Anonymous class có thể khai báo một field cùng tên với field của enclosing class.

Tạo **`AnonymousFieldShadowDemo.java`**:

```java
class Outer {
    private final String name = "OUTER";

    void show() {
        Runnable task = new Runnable() {
            private final String name = "ANON";

            @Override
            public void run() {
                System.out.println("short=" + name);
                System.out.println("this=" + this.name);
                System.out.println("outer=" + Outer.this.name);
            }
        };

        task.run();
    }
}

public class AnonymousFieldShadowDemo {
    public static void main(String[] args) {
        new Outer().show();
    }
}
```

```bash
javac AnonymousFieldShadowDemo.java
java AnonymousFieldShadowDemo
```

```text
short=ANON
this=ANON
outer=OUTER
```

**Vì sao `name` chọn ANON?** Anonymous class khai báo field `name` gần hơn, nên một tên đơn giản trong `run` không tự chọn Outer field. `Outer.this.name` định danh rõ nơi chứa field.

**`private` không cản truy cập ở ví dụ này:** Java cho phép các nested/anonymous classes hợp lệ truy cập private members của enclosing class theo quy tắc truy cập giữa các lớp trong nest.

## 6. Tham số của anonymous method có thể che cả hai fields

Nếu chính method của anonymous class có tham số cùng tên, tên không định danh ưu tiên tham số.

Tạo **`AnonymousParameterShadowDemo.java`**:

```java
interface Reporter {
    void report(String name);
}

class Outer {
    private final String name = "OUTER";

    Reporter create() {
        return new Reporter() {
            private final String name = "ANON";

            @Override
            public void report(String name) {
                System.out.println("parameter=" + name);
                System.out.println("anonymous=" + this.name);
                System.out.println("outer=" + Outer.this.name);
            }
        };
    }
}

public class AnonymousParameterShadowDemo {
    public static void main(String[] args) {
        Reporter reporter = new Outer().create();
        reporter.report("ARGUMENT");
    }
}
```

```bash
javac AnonymousParameterShadowDemo.java
java AnonymousParameterShadowDemo
```

```text
parameter=ARGUMENT
anonymous=ANON
outer=OUTER
```

Ba nơi lưu dữ liệu không giống nhau:

- `name`: tham số của một lần gọi `report`.
- `this.name`: field của anonymous reporter object.
- `Outer.this.name`: field của enclosing Outer object.

**Kiến thức chuyển giao:** Khi tên trùng, hãy viết receiver/qualification chính xác thay vì đoán compiler có chọn outer state hay không. Một nhầm lẫn có thể **biên dịch thành công nhưng sửa sai đối tượng**.

## 7. Ví dụ mutate sai field nếu bỏ `Outer.this`

Tạo **`AnonymousStateUpdateDemo.java`**:

```java
class Account {
    private int count;

    Runnable updater() {
        return new Runnable() {
            private int count = 100;

            @Override
            public void run() {
                this.count++;
                Account.this.count++;
                System.out.println("anonymous=" + this.count);
                System.out.println("account=" + Account.this.count);
            }
        };
    }

    int count() {
        return count;
    }
}

public class AnonymousStateUpdateDemo {
    public static void main(String[] args) {
        Account account = new Account();
        Runnable updater = account.updater();

        updater.run();
        updater.run();

        System.out.println("outside account=" + account.count());
    }
}
```

```bash
javac AnonymousStateUpdateDemo.java
java AnonymousStateUpdateDemo
```

```text
anonymous=101
account=1
anonymous=102
account=2
outside account=2
```

- `this.count++` tăng **field của anonymous object**; nó bắt đầu 100.
- `Account.this.count++` tăng **field của Account object**; nó bắt đầu 0.
- Hai lần gọi `run()` trên cùng anonymous object giữ state `count` của nó qua các lần gọi.

**Nếu business intent chỉ là tăng Account.count**, viết `Account.this.count++` hoặc gọi một method có tên rõ trên Account. Không dùng tên `count++` khi anonymous class cũng có field count nếu việc chọn receiver dễ gây hiểu nhầm.

## 8. `Outer.this` là receiver đến đúng Outer object được gắn với callback

Một anonymous callback tạo ở Outer instance A sẽ tiếp tục trỏ A dù được gọi từ một nơi khác hay sau khi method tạo nó đã return.

Tạo **`AnonymousOwnerIdentityDemo.java`**:

```java
class Outer {
    private final String id;

    Outer(String id) {
        this.id = id;
    }

    Runnable callback() {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println(Outer.this.id);
            }
        };
    }
}

public class AnonymousOwnerIdentityDemo {
    public static void main(String[] args) {
        Outer first = new Outer("FIRST");
        Outer second = new Outer("SECOND");

        Runnable one = first.callback();
        Runnable two = second.callback();

        two.run();
        one.run();
    }
}
```

```bash
javac AnonymousOwnerIdentityDemo.java
java AnonymousOwnerIdentityDemo
```

```text
SECOND
FIRST
```

Khi `two.run()` gọi trước, callback vẫn lấy `SECOND` từ Outer thứ hai. `one.run()` lấy `FIRST` từ Outer thứ nhất.

`Outer.this` **không tìm Outer object mới nhất vừa được tạo**; nó chỉ enclosing instance cụ thể theo lexical/instance context khi anonymous object được tạo.

## 9. Truy cập instance methods thay vì trực tiếp sửa outer field

`Outer.this` còn cho phép gọi method của enclosing Outer object:

```java
Outer.this.registerEvent();
```

Nếu anonymous class cũng có method `registerEvent()`, việc dùng receiver càng quan trọng.

Tạo **`AnonymousMethodReceiverDemo.java`**:

```java
class Outer {
    String label() {
        return "OUTER";
    }

    Runnable callback() {
        return new Runnable() {
            String label() {
                return "ANONYMOUS";
            }

            @Override
            public void run() {
                System.out.println(label());
                System.out.println(this.label());
                System.out.println(Outer.this.label());
            }
        };
    }
}

public class AnonymousMethodReceiverDemo {
    public static void main(String[] args) {
        new Outer().callback().run();
    }
}
```

```bash
javac AnonymousMethodReceiverDemo.java
java AnonymousMethodReceiverDemo
```

```text
ANONYMOUS
ANONYMOUS
OUTER
```

`label()` và `this.label()` đều chọn method của anonymous class. `Outer.this.label()` **gọi instance method trên Outer receiver**.

Một tên method trùng tên ở hai classes có thể chịu quy tắc method lookup/overload/override riêng; nguyên tắc thực tiễn là **định danh receiver rõ ràng** khi intent khác nhau.

## 10. `this` và `Outer.this` ở anonymous class có nhiều tầng bao ngoài

Giả sử anonymous class được tạo từ instance method của **non-static inner class** `Middle`, mà Middle là member inner class của `Outer`.

Tạo **`AnonymousMultipleEnclosingDemo.java`**:

```java
class Outer {
    private final String label = "OUTER";

    class Middle {
        private final String label = "MIDDLE";

        Runnable callback() {
            return new Runnable() {
                private final String label = "ANON";

                @Override
                public void run() {
                    System.out.println(this.label);
                    System.out.println(Middle.this.label);
                    System.out.println(Outer.this.label);
                }
            };
        }
    }
}

public class AnonymousMultipleEnclosingDemo {
    public static void main(String[] args) {
        Outer outer = new Outer();
        Outer.Middle middle = outer.new Middle();
        middle.callback().run();
    }
}
```

```bash
javac AnonymousMultipleEnclosingDemo.java
java AnonymousMultipleEnclosingDemo
```

```text
ANON
MIDDLE
OUTER
```

Receiver tương ứng:

| Expression | Đối tượng |
| --- | --- |
| `this` | Anonymous Runnable instance |
| `Middle.this` | Enclosing Middle instance |
| `Outer.this` | Enclosing Outer instance |

**Điểm cần kiểm:** `Middle.this` và `Outer.this` có nghĩa vì anonymous class được khai báo trong instance context gắn với các enclosing objects ấy. Không phải mọi anonymous class ở mọi vị trí đều có toàn bộ các qualified-this expressions này.

## 11. Local class bên trong anonymous class có thêm một tầng `this`

Có thể có thêm một local named class được khai báo trong method của anonymous class. Khi ấy `this` trong local class trỏ đến **local instance**, không phải anonymous instance.

Đối với anonymous enclosing class, nó **không có source-level tên** để viết kiểu `AnonymousName.this`. Một cách rõ ràng là lưu `this` của anonymous class vào biến reference có supertype phù hợp rồi để local class capture nó.

Tạo **`AnonymousAndLocalThisDemo.java`**:

```java
interface Task {
    String id();
    void run();
}

class Outer {
    private final String id = "OUTER";

    Task create() {
        return new Task() {
            private final String id = "ANON";

            @Override
            public String id() {
                return id;
            }

            @Override
            public void run() {
                Task anonymousSelf = this;

                class LocalHelper {
                    private final String id = "LOCAL";

                    void print() {
                        System.out.println("local=" + this.id);
                        System.out.println("anonymous=" +
                                anonymousSelf.id());
                        System.out.println("outer=" + Outer.this.id);
                    }
                }

                new LocalHelper().print();
            }
        };
    }
}

public class AnonymousAndLocalThisDemo {
    public static void main(String[] args) {
        new Outer().create().run();
    }
}
```

```bash
javac AnonymousAndLocalThisDemo.java
java AnonymousAndLocalThisDemo
```

```text
local=LOCAL
anonymous=ANON
outer=OUTER
```

**Vì sao biến `anonymousSelf`?** Anonymous class không có tên để dùng một qualified-this expression dạng tên class. Nhưng `this` trong `run()` là một Task reference tới anonymous object; local helper có thể capture reference ấy vì nó effectively final.

Đừng nhầm `Outer.this` trong local helper với anonymous self: nó vẫn là enclosing Outer instance.

## 12. `this` của anonymous khác `this` trong lambda

Một lambda expression **không cung cấp một receiver `this` mới**. `this` trong lambda biểu thị lexical enclosing receiver.

Tạo **`AnonymousVersusLambdaThisDemo.java`**:

```java
class Outer {
    private final String label = "OUTER";

    void compare() {
        Runnable anonymous = new Runnable() {
            private final String label = "ANON";

            @Override
            public void run() {
                System.out.println("anonymous this=" +
                        this.label);
                System.out.println("anonymous outer=" +
                        Outer.this.label);
            }
        };

        Runnable lambda = () -> {
            System.out.println("lambda this=" + this.label);
            System.out.println("lambda outer=" +
                    Outer.this.label);
        };

        anonymous.run();
        lambda.run();
    }
}

public class AnonymousVersusLambdaThisDemo {
    public static void main(String[] args) {
        new Outer().compare();
    }
}
```

```bash
javac AnonymousVersusLambdaThisDemo.java
java AnonymousVersusLambdaThisDemo
```

```text
anonymous this=ANON
anonymous outer=OUTER
lambda this=OUTER
lambda outer=OUTER
```

Trong `Outer.compare()`:

- Anonymous class tự có một receiver `this` = anonymous Runnable object.
- Lambda sử dụng lexical `this` = Outer object của `compare`.
- `Outer.this` ở cả hai trường hợp có thể dùng trong ngữ cảnh instance này để chỉ rõ enclosing Outer object.

**Kết luận khi refactor:** Đổi một anonymous class thành lambda có thể làm `this` đổi nghĩa. Dù cả hai đều đáp ứng `Runnable`, không thể thay thế chỉ bằng xóa `new Runnable() { ... }` nếu body dùng `this` hoặc những member lookups phụ thuộc receiver.

## 13. Lambda viết trong method của anonymous class: lexical `this` là anonymous object

Đừng diễn giải quá đơn giản rằng “lambda lúc nào cũng dùng Outer.this”. Lambda dùng **lexical enclosing `this` ở chính nơi lambda được viết**.

Tạo **`LambdaInsideAnonymousDemo.java`**:

```java
class Outer {
    private final String label = "OUTER";

    Runnable create() {
        return new Runnable() {
            private final String label = "ANON";

            @Override
            public void run() {
                Runnable nestedLambda = () -> {
                    System.out.println("this=" + this.label);
                    System.out.println("outer=" +
                            Outer.this.label);
                };

                nestedLambda.run();
            }
        };
    }
}

public class LambdaInsideAnonymousDemo {
    public static void main(String[] args) {
        new Outer().create().run();
    }
}
```

```bash
javac LambdaInsideAnonymousDemo.java
java LambdaInsideAnonymousDemo
```

```text
this=ANON
outer=OUTER
```

Ở đây lambda được viết **bên trong instance method của anonymous class**. Lexical `this` của lambda là **anonymous object**, nên `this.label` là ANON. `Outer.this.label` vẫn nhắm Outer.

Quy tắc chính xác:

- Lambda trong `Outer.instanceMethod` → `this` là Outer.
- Lambda trong `anonymous.run()` → `this` là anonymous object.
- Lambda trong `Inner.instanceMethod` → `this` là Inner.
- Với static context không có lexical `this`, không thể dùng `this` như thể có instance.

## 14. Một lỗi khi chuyển anonymous class sang lambda

Giả sử anonymous callback viết:

```java
Runnable old = new Runnable() {
    @Override
    public void run() {
        System.out.println(this.getClass().isAnonymousClass());
    }
};
```

Ở đây `this` là anonymous object, nên `isAnonymousClass()` trả true.

Nếu refactor thành:

```java
Runnable replacement = () ->
        System.out.println(this.getClass().isAnonymousClass());
```

thì `this` trỏ lexical enclosing receiver (nếu code nằm trong một instance method có receiver). Nó không còn là anonymous object. Kết quả có thể khác. Trong static context, dòng lambda dùng `this` thậm chí không hợp lệ.

**Không dùng `getClass().getName()` để xác định lambda/anonymous name bằng chuỗi cố định.** Nếu cần identity behavior, kiểm contract của callback và gọi đúng receiver thay vì dựa vào compiler/runtime class name.

## 15. `Outer.this` không phải cách truy cập field static

Với field `static`, cách viết rõ ràng là `Outer.shared`. `Outer.this` dành cho **enclosing instance**.

Tạo **`AnonymousStaticAndInstanceDemo.java`**:

```java
class Outer {
    static final String CATEGORY = "STATIC";
    private final String id = "INSTANCE";

    Runnable task() {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println(Outer.CATEGORY);
                System.out.println(Outer.this.id);
            }
        };
    }
}

public class AnonymousStaticAndInstanceDemo {
    public static void main(String[] args) {
        new Outer().task().run();
    }
}
```

```bash
javac AnonymousStaticAndInstanceDemo.java
java AnonymousStaticAndInstanceDemo
```

```text
STATIC
INSTANCE
```

`Outer.CATEGORY` đọc static member trên type. `Outer.this.id` đọc instance member trên enclosing Outer object.

**Không nhầm** `Outer.class` (Class object mô tả kiểu Outer) với `Outer.this` (Outer instance). Chúng là các expressions hoàn toàn khác nhau.

## 16. Anonymous class tạo trong static method không có enclosing Outer instance tự động

Có thể tạo anonymous class từ static method, nhưng static method **không có `this` là Outer**.

Tạo **`AnonymousInStaticContextDemo.java`**:

```java
class Outer {
    private final String label;

    Outer(String label) {
        this.label = label;
    }

    static Runnable create(Outer owner) {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println(owner.label);
                System.out.println(
                        this.getClass().isAnonymousClass());

                // Outer.this.label không hợp lệ ở đây.
            }
        };
    }
}

public class AnonymousInStaticContextDemo {
    public static void main(String[] args) {
        Outer owner = new Outer("EXPLICIT");
        Outer.create(owner).run();
    }
}
```

```bash
javac AnonymousInStaticContextDemo.java
java AnonymousInStaticContextDemo
```

```text
EXPLICIT
true
```

- `this` trong `run` vẫn là anonymous object, kể cả anonymous class được tạo bởi static method.
- `Outer.this` không hợp lệ ở vị trí này: static method không có implicit enclosing Outer receiver.
- `owner` là **parameter effectively final** được anonymous class capture; nó được truyền vào rõ ràng.
- Truy cập `owner.label` ở code này được phép theo nested/private access rules tương ứng.

**Cần phân biệt:** Không có `Outer.this` không có nghĩa anonymous class không được dùng Outer object. Nó chỉ có nghĩa không có **implicit enclosing instance** của Outer; một reference explicit vẫn có thể được truyền và dùng.

## 17. Static nested class cũng không tự có `Outer.this`

Một `static class Nested` được khai báo bên trong `Outer` không có implicit enclosing Outer instance như non-static inner class.

Nếu trong static nested class tạo anonymous callback:

```java
class Outer {
    private int value = 10;

    static class Nested {
        Runnable task(Outer owner) {
            return new Runnable() {
                @Override
                public void run() {
                    System.out.println(owner.value);
                    // Outer.this.value; // Không hợp lệ.
                }
            };
        }
    }
}
```

Đây là **class declaration hợp lệ**, không có `main`. `owner` là parameter của `Nested.task`, được capture. `Outer.this` không có implicit Outer instance tại lexical context đó.

Nếu anonymous class được tạo trong một **non-static member inner class**, có thể có `Inner.this` và `Outer.this` tương ứng như phần nhiều tầng trước.

**Đừng suy rằng chỉ vì mã có dấu `Outer.Nested` hoặc nằm trong cùng file Outer, `Outer.this` sẽ hợp lệ.** Nó phụ thuộc ngữ cảnh instance và enclosing relationship.

## 18. `this` trong static method khai báo bởi anonymous class?

Một anonymous class có thể implement một interface mà phương thức `run` là **instance method**; vì vậy body của `run` có `this` là anonymous object.

Tuy nhiên không thể dùng `this` trực tiếp trong **static context** chỉ vì ở bên trong một method tạo anonymous object. Ví dụ:

```java
static void create() {
    // this.toString(); // Không hợp lệ: static method.
    Runnable task = new Runnable() {
        @Override
        public void run() {
            System.out.println(this.toString()); // Hợp lệ.
        }
    };
}
```

Đây là **mảnh static method minh họa**. Vị trí của expression mới quyết định ý nghĩa `this`:

- Trước biểu thức tạo anonymous object, đang ở static method, không có receiver.
- Trong `run` của anonymous class, có instance receiver của anonymous object.

**Không nhầm thời điểm khởi tạo và phạm vi chữ khóa.** Compiler xác định instance/static context theo cấu trúc ngôn ngữ, không phụ thuộc việc method nào sẽ được gọi trước.

## 19. Anonymous class có thể khai báo field và instance initializer

Dù không có constructor mang tên class, anonymous class có thể có instance initializer để thiết lập state.

Tạo **`AnonymousInitializationDemo.java`**:

```java
class Outer {
    private final String id = "OWNER";

    Runnable create() {
        return new Runnable() {
            private String label;

            {
                label = Outer.this.id + "-TASK";
            }

            @Override
            public void run() {
                System.out.println(this.label);
                System.out.println(Outer.this.id);
            }
        };
    }
}

public class AnonymousInitializationDemo {
    public static void main(String[] args) {
        new Outer().create().run();
    }
}
```

```bash
javac AnonymousInitializationDemo.java
java AnonymousInitializationDemo
```

```text
OWNER-TASK
OWNER
```

- `label` là field của anonymous object.
- Instance initializer `{ ... }` chạy trong quá trình anonymous instance được khởi tạo và dùng `Outer.this.id` của enclosing Outer.
- Trong `run`, `this.label` trả field anonymous; `Outer.this.id` trả field Outer.

**Cảnh báo lifecycle:** Đừng để anonymous object `this` thoát ra ngoài quá sớm trong initializer/constructor path, đặc biệt khi fields hoặc enclosing owner chưa khởi tạo đầy đủ. Điều này có thể làm lộ partial state.

## 20. Truy cập member private của Outer từ anonymous class

Vì anonymous class được khai báo trong lexical context phù hợp, nó có thể truy cập private members của Outer theo Java nested-class access rules.

Tạo **`AnonymousPrivateAccessDemo.java`**:

```java
class Outer {
    private int balance = 100;

    private void deposit(int amount) {
        balance += amount;
    }

    Runnable makeDeposit(int amount) {
        return new Runnable() {
            @Override
            public void run() {
                Outer.this.deposit(amount);
                System.out.println(Outer.this.balance);
            }
        };
    }
}

public class AnonymousPrivateAccessDemo {
    public static void main(String[] args) {
        Outer outer = new Outer();
        Runnable command = outer.makeDeposit(25);
        command.run();
        command.run();
    }
}
```

```bash
javac AnonymousPrivateAccessDemo.java
java AnonymousPrivateAccessDemo
```

```text
125
150
```

`Outer.this.deposit` gọi một private instance method của Outer, từ code anonymous class hợp lệ. `amount` là effectively-final method parameter được capture. Hai lần gọi `run` mutate **cùng enclosing Outer object**.

**Điều kiện truy cập:** Không có nghĩa mọi class ở khắp nơi được đọc private field chỉ vì có Outer reference. Đây là quyền truy cập trong phạm vi nested/enclosing class do Java quy định, không phải phá encapsulation.

## 21. Phân biệt `this`, `super` và `Outer.this`

Trong một anonymous class:

- `this`: receiver của **anonymous class**.
- `super`: phần superclass của **anonymous object**, theo inheritance rules.
- `Outer.this`: **enclosing Outer instance** trong lexical context hợp lệ.

Đừng nhầm `super` với “đối tượng bao ngoài”. Anonymous class không tự extends Outer chỉ vì được viết trong Outer.

Tạo **`AnonymousSuperVersusOuterDemo.java`**:

```java
class Base {
    String kind() {
        return "BASE";
    }
}

class Outer {
    private final String name = "OUTER";

    Base create() {
        return new Base() {
            @Override
            String kind() {
                return "ANON";
            }

            String detail() {
                return super.kind() + "/" +
                        this.kind() + "/" +
                        Outer.this.name;
            }

            @Override
            public String toString() {
                return detail();
            }
        };
    }
}

public class AnonymousSuperVersusOuterDemo {
    public static void main(String[] args) {
        Base result = new Outer().create();
        System.out.println(result.kind());
        System.out.println(result.toString());
    }
}
```

```bash
javac AnonymousSuperVersusOuterDemo.java
java AnonymousSuperVersusOuterDemo
```

```text
ANON
BASE/ANON/OUTER
```

`super.kind()` gọi Base implementation. `this.kind()` gọi override của anonymous class. `Outer.this.name` lấy field thuộc enclosing Outer, không liên quan chuỗi kế thừa Base.

Để gọi method `detail()` từ main, static type Base không khai báo nó; ví dụ expose behavior qua override `toString()`, là method có trong Object và có thể gọi qua Base.

## 22. Biến có static type interface không cho gọi method riêng của anonymous class

Một anonymous class có thể khai báo helper method riêng nhưng caller giữ nó qua `Runnable` chỉ thấy methods hợp lệ theo static type `Runnable`.

Tạo **`AnonymousHiddenMethodDemo.java`**:

```java
public class AnonymousHiddenMethodDemo {
    public static void main(String[] args) {
        Runnable task = new Runnable() {
            private int count;

            private void increment() {
                count++;
            }

            @Override
            public void run() {
                this.increment();
                System.out.println(count);
            }
        };

        task.run();
        task.run();

        // task.increment(); // Không hợp lệ:
        // Runnable không có method increment().
    }
}
```

```bash
javac AnonymousHiddenMethodDemo.java
java AnonymousHiddenMethodDemo
```

```text
1
2
```

`increment()` thuộc anonymous class và được gọi hợp lệ **trong chính body của nó qua `this`**. Biến task bên ngoài có static type Runnable, chỉ expose contract Runnable/Object tương ứng.

**Phân biệt compile-time và runtime:** Object thực tế có method private increment, nhưng code bên ngoài không tự có quyền truy cập hay tên method vì static type và access control.

Nếu caller cần nhiều methods, nên định nghĩa **interface có đúng các methods cần thiết**, hoặc dùng named local/member class tại phạm vi cần dùng; không cố ép mọi API vào Runnable.

## 23. Anonymous class không có tên để viết `Anonymous.this`

Lớp vô danh khác local named class:

```java
class Local {
    void show() {
        System.out.println(Local.this);
    }
}
```

Đây là **mảnh khai báo local class** trong block; nó có tên Local nên có thể dùng qualified this theo context thích hợp.

Trong anonymous class, bạn **không có một source-level class name** để viết dạng `Anonymous.this`. Muốn chỉ chính anonymous instance từ method của nó, chỉ cần `this`. Muốn chỉ enclosing instance có tên, dùng `Outer.this` / `Inner.this` nếu lexical context hợp lệ.

Nếu anonymous instance cần được dùng bên trong một local class lồng sâu thêm, có thể giữ nó trong biến supertype `Runnable anonymousSelf = this;` rồi capture biến này, như ví dụ ở mục nhiều tầng.

**Không dùng tên compiler-generated** như `Outer$1.this`. Binary names không phải tên Java source-level được bảo đảm cho anonymous class.

## 24. `this` trong anonymous class có thể được truyền cho API khác

Trong body anonymous class, `this` có type anonymous class, cũng phù hợp với interface/superclass mà nó implement/extends.

Tạo **`AnonymousPassSelfDemo.java`**:

```java
class Outer {
    private static void inspect(Runnable callback) {
        System.out.println(callback != null);
        System.out.println(
                callback.getClass().isAnonymousClass());
    }

    Runnable create() {
        return new Runnable() {
            @Override
            public void run() {
                inspect(this);
                System.out.println(Outer.this != null);
            }
        };
    }
}

public class AnonymousPassSelfDemo {
    public static void main(String[] args) {
        new Outer().create().run();
    }
}
```

```bash
javac AnonymousPassSelfDemo.java
java AnonymousPassSelfDemo
```

```text
true
true
true
```

`inspect(this)` truyền **anonymous Runnable instance**. `Outer.this != null` trong instance context hợp lệ luôn true đối với một enclosing instance đang tồn tại ở ví dụ.

**Về GC/lifecycle:** Nếu một registry lưu callback reference, anonymous object có thể sống lâu; nếu nó duy trì reference tới enclosing Outer (do sử dụng Outer.this), Outer cũng có thể được giữ reachable qua callback. Đây không phải lỗi cú pháp nhưng là rủi ro thiết kế khi callbacks sống dài.

## 25. Callback tạo trong Outer nhưng chạy ở một nơi khác

Một callback có thể được tạo ở Outer object A rồi chạy sau đó, kể cả từ code không biết tên Outer class. `Outer.this` trong callback vẫn nhắm A.

Tạo **`AnonymousDeferredCallbackDemo.java`**:

```java
class Outer {
    private final String id;

    Outer(String id) {
        this.id = id;
    }

    Runnable task() {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println("callback for " +
                        Outer.this.id);
            }
        };
    }
}

public class AnonymousDeferredCallbackDemo {
    static void execute(Runnable runnable) {
        runnable.run();
    }

    public static void main(String[] args) {
        Runnable saved;

        {
            Outer owner = new Outer("A");
            saved = owner.task();
        }

        execute(saved);
    }
}
```

```bash
javac AnonymousDeferredCallbackDemo.java
java AnonymousDeferredCallbackDemo
```

```text
callback for A
```

Sau khi block chứa biến owner kết thúc, callback vẫn giữ khả năng tham chiếu tới Outer A. **Scope của biến owner** kết thúc không có nghĩa instance A bị hủy ngay; reference graph quyết định object còn reachable hay không.

**Lưu ý concurrency:** Nếu callback được chạy ở thread khác, các quy tắc safe publication, mutable state và synchronization vẫn áp dụng. `Outer.this` không tự tạo happens-before hoặc thread safety.

## 26. Capture local variables: effectively final

Anonymous class có thể đọc local variables và parameters của enclosing method, khi các biến đó **final hoặc effectively final**.

Tạo **`AnonymousCaptureDemo.java`**:

```java
class Outer {
    Runnable makePrinter(String prefix) {
        int suffix = 7;

        return new Runnable() {
            @Override
            public void run() {
                System.out.println(prefix + suffix);
            }
        };
    }
}

public class AnonymousCaptureDemo {
    public static void main(String[] args) {
        Runnable printer = new Outer().makePrinter("ID-");
        printer.run();
    }
}
```

```bash
javac AnonymousCaptureDemo.java
java AnonymousCaptureDemo
```

```text
ID-7
```

- `prefix` là method parameter, được capture.
- `suffix` là local variable của method.
- Cả hai không bị gán lại nên effectively final.
- Anonymous object vẫn có thể sử dụng dữ liệu đã capture sau khi `makePrinter` return.

### Anti-example: gán lại local variable

```java
int suffix = 7;
Runnable wrong = new Runnable() {
    @Override
    public void run() {
        System.out.println(suffix);
    }
};
suffix = 8; // Lỗi compile-time khi suffix được capture.
```

Đây là **mảnh minh họa lỗi** trong một method. Điều kiện effectively final không cho gán lại biến local đã được anonymous class capture theo cách này.

**`Outer.this` không dùng để sửa captured local variable**: `Outer.this` chỉ instance Outer, trong khi suffix là local variable của method, không phải field Outer.

## 27. Capture reference tới mutable object không đóng băng object

Một captured local variable có thể effectively final dù object được tham chiếu vẫn mutable. Đây là điều cần biết để tránh nhầm “capture” với “copy”.

Tạo **`AnonymousCapturedMutableDemo.java`**:

```java
public class AnonymousCapturedMutableDemo {
    public static void main(String[] args) {
        StringBuilder buffer = new StringBuilder("A");

        Runnable action = new Runnable() {
            @Override
            public void run() {
                buffer.append("X");
                System.out.println(buffer.toString());
            }
        };

        action.run();
        buffer.append("B");
        action.run();
    }
}
```

```bash
javac AnonymousCapturedMutableDemo.java
java AnonymousCapturedMutableDemo
```

```text
AX
AXBX
```

`buffer` không bị gán sang một StringBuilder khác, nhưng nội dung StringBuilder bị mutate. Anonymous object và main đang thao tác với **cùng buffer object**.

Nếu ý định là snapshot immutable text, hãy tạo `String snapshot = buffer.toString();` rồi capture snapshot, thay vì giữ mutable buffer reference. Nếu sharing mutable state là chủ ý, ghi rõ ownership và thread-safety contract.

## 28. Sửa outer field hay sửa anonymous field — một bài test tự động

Dùng một chương trình có helper `check` để kiểm **đúng receiver bị thay đổi**, không chỉ nhìn stdout.

Tạo **`AnonymousReceiverSelfTest.java`**:

```java
class Outer {
    private int outerCount = 0;

    Runnable action() {
        return new Runnable() {
            private int innerCount = 0;

            @Override
            public void run() {
                this.innerCount++;
                Outer.this.outerCount++;

                if (innerCount != outerCount) {
                    throw new AssertionError(
                            "unexpected receiver state");
                }
            }
        };
    }

    int outerCount() {
        return outerCount;
    }
}

public class AnonymousReceiverSelfTest {
    static void check(boolean condition, String label) {
        if (!condition) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        Outer owner = new Outer();
        Runnable action = owner.action();

        action.run();
        check(owner.outerCount() == 1, "first update");

        action.run();
        check(owner.outerCount() == 2, "second update");

        System.out.println("receiver checks PASS");
    }
}
```

```bash
javac AnonymousReceiverSelfTest.java
java AnonymousReceiverSelfTest
```

```text
receiver checks PASS
```

Bài test kiểm outerCount từ bên ngoài; trong anonymous `run` kiểm innerCount bằng outerCount. `AssertionError` được ném chủ động, không cần bật JVM assertions bằng `-ea`.

**Đây là test ví dụ đơn luồng**, không chứng minh thread safety. Nếu nhiều anonymous callbacks cùng cập nhật outerCount đồng thời, cần concurrency contract riêng; `++` không atomic chỉ vì dùng `Outer.this`.

## 29. Qualified this cũng có thể dùng trong method reference

Một anonymous class có thể trả `Supplier` bound vào enclosing Outer instance bằng method reference:

```java
return Outer.this::label;
```

Tạo **`AnonymousOuterMethodReferenceDemo.java`**:

```java
import java.util.function.Supplier;

class Outer {
    private final String label;

    Outer(String label) {
        this.label = label;
    }

    String label() {
        return label;
    }

    Supplier<String> create() {
        return new Supplier<String>() {
            @Override
            public String get() {
                Supplier<String> outerLabel =
                        Outer.this::label;
                return outerLabel.get();
            }
        };
    }
}

public class AnonymousOuterMethodReferenceDemo {
    public static void main(String[] args) {
        Supplier<String> supplier =
                new Outer("OWNER").create();

        System.out.println(supplier.get());
    }
}
```

```bash
javac AnonymousOuterMethodReferenceDemo.java
java AnonymousOuterMethodReferenceDemo
```

```text
OWNER
```

`Outer.this::label` là **bound instance method reference**. Nó dùng enclosing Outer object làm receiver, không dùng anonymous supplier. Có thể gọi trực tiếp `Outer.this.label()` trong ví dụ; method reference được minh họa khi API cần một functional value.

## 30. `Outer.this` và biến tham chiếu explicit khác nhau thế nào?

Một anonymous class có thể vừa có `Outer.this`, vừa giữ một biến `otherOwner` tham chiếu một Outer instance khác.

Tạo **`AnonymousTwoOwnersDemo.java`**:

```java
class Outer {
    private final String id;

    Outer(String id) {
        this.id = id;
    }

    Runnable compareWith(Outer otherOwner) {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println("enclosing=" +
                        Outer.this.id);
                System.out.println("explicit=" +
                        otherOwner.id);
                System.out.println(
                        Outer.this == otherOwner);
            }
        };
    }
}

public class AnonymousTwoOwnersDemo {
    public static void main(String[] args) {
        Outer first = new Outer("A");
        Outer second = new Outer("B");

        first.compareWith(second).run();
    }
}
```

```bash
javac AnonymousTwoOwnersDemo.java
java AnonymousTwoOwnersDemo
```

```text
enclosing=A
explicit=B
false
```

`Outer.this` là enclosing instance A vì method `compareWith` được gọi trên first. `otherOwner` là captured parameter chứa reference B, không phải enclosing instance. Hai expressions có thể có cùng Java type Outer nhưng **không cùng object**.

Đừng thay `Outer.this` bằng một biến named owner khi semantics yêu cầu chính enclosing object, trừ khi bạn cố ý chọn explicit reference và kiểm đúng identity.

## 31. Anonymous class khi extends abstract class

Anonymous class không chỉ dùng với interfaces. Có thể tạo subclass vô danh của abstract class hoặc subclass được phép mở rộng.

Tạo **`AnonymousAbstractSuperclassDemo.java`**:

```java
abstract class Formatter {
    abstract String format(int number);
}

class Outer {
    private final String prefix;

    Outer(String prefix) {
        this.prefix = prefix;
    }

    Formatter formatter() {
        return new Formatter() {
            @Override
            String format(int number) {
                return Outer.this.prefix + number;
            }
        };
    }
}

public class AnonymousAbstractSuperclassDemo {
    public static void main(String[] args) {
        Formatter formatter =
                new Outer("N-").formatter();

        System.out.println(formatter.format(12));
    }
}
```

```bash
javac AnonymousAbstractSuperclassDemo.java
java AnonymousAbstractSuperclassDemo
```

```text
N-12
```

Anonymous class **extends Formatter** và override abstract method. `this` trong `format` là formatter anonymous instance; `Outer.this` là Outer đang bao ngoài và chứa `prefix`.

**Phân biệt thứ bậc:** Formatter là superclass của anonymous object; Outer là lexical enclosing object, không nhất thiết nằm trên inheritance chain của Formatter.

## 32. `Outer.this` có thể giữ outer instance lâu hơn mong muốn

Khi lưu anonymous callback vào một collection hoặc event bus có vòng đời dài hơn outer component, callback có thể khiến outer object vẫn reachable. Đây là vấn đề thiết kế, không phải cú pháp sai.

Sơ đồ:

```text
Long-lived registry
       |
       v
Anonymous callback
       |
       +--- enclosing/captured reference ---> Outer component
```

Nếu Outer chứa UI components, caches hoặc resources, việc giữ callback lâu có thể giữ cả các objects ấy.

**Hướng giảm rủi ro:**

- Đăng ký và **hủy đăng ký callbacks** đúng lifecycle.
- Khi chỉ cần một vài immutable values, capture **snapshot values** thay vì toàn bộ Outer instance.
- Dùng helper được truyền dependencies nhỏ nhất cần thiết; static nested class hoặc lambda không dùng `this`/Outer fields có thể giảm coupling, tùy implementation và runtime semantics.
- Nếu ứng dụng thực sự cần weak references, thiết kế rõ độ tin cậy của callback và xử lý trường hợp target đã bị GC; không dùng weak reference máy móc.

**Không suy rằng mọi anonymous class đều giữ Outer** bất kể có dùng outer state hay không. Kiểu implementation và yêu cầu ngôn ngữ tại context ảnh hưởng object graph; phần mềm nên dựa vào behavior/ownership contract và kiểm memory retention thực tế khi cần.

## 33. Có nên gọi `Outer.this` từ anonymous callback thay vì public accessor?

Trong code nested hợp lệ, cả:

```java
Outer.this.count
```

và:

```java
Outer.this.count()
```

có thể hợp lệ nếu field/method tương ứng tồn tại. Nhưng **khi cần bảo vệ invariants**, thường nên gọi một method có ý nghĩa:

```java
Outer.this.recordEvent();
```

thay vì sửa trực tiếp nhiều private fields từ callback. Method của Outer có thể validate, cập nhật state nhất quán hoặc kiểm quyền.

**Điểm thiết kế:** Dùng `Outer.this` không đồng nghĩa bypass encapsulation ở cấp nghiệp vụ. Nó chỉ chọn đúng receiver; việc mutate nên tuân theo invariant/lifecycle của owner.

## 34. Lỗi compile-time thường gặp

| Biểu thức / ý định | Kết quả hoặc điều kiện |
| --- | --- |
| `this.field` trong anonymous instance method | Đọc field của anonymous receiver nếu khai báo/tra cứu hợp lệ |
| `Outer.this.field` trong anonymous class tạo ở Outer instance context | Đọc enclosing Outer receiver nếu hợp lệ |
| `Outer.this.field` trong anonymous class tạo từ static method Outer | Không có implicit enclosing Outer instance → không hợp lệ |
| `Outer.staticField` | Truy cập static field qua type Outer |
| `Outer.class` | Class metadata, không phải enclosing instance |
| `this == Outer.this` | Hai reference types có thể không comparable theo compile-time rules; dùng cast chung Object nếu kiểm identity được phép |
| `Outer.this = owner` | Không hợp lệ: qualified this không phải assignable variable |
| `Outer.this.method()` | Gọi instance method trên enclosing Outer |
| `super.method()` trong anonymous class | Theo superclass của anonymous object, không phải outer |
| `new Runnable(){...}` | Tạo anonymous class instance |
| `new Runnable() -> ...` | Không phải cú pháp lambda |
| `this` bên trong lambda trong Outer instance method | Receiver lexical Outer |
| `this` bên trong lambda trong anonymous instance method | Receiver lexical anonymous object |
| `anonymousSpecificMethod()` qua biến Runnable | Chỉ hợp lệ nếu static type Runnable cho phép tên/signature ấy; thường không |
| `Anonymous.this` | Không có tên source-level “Anonymous” của anonymous class để định danh |
| `Inner.this` trong anonymous class khai báo trong Inner instance context | Hợp lệ nếu có enclosing Inner instance phù hợp |
| `Outer.this` trong static nested class/helper không có Outer instance | Không hợp lệ; dùng explicit owner reference |

**Lưu ý:** Các ví dụ lỗi trong bảng là để nhận diện quy tắc, không phải toàn bộ các dòng đều là source runnable độc lập.

## 35. Bài tập dự đoán kết quả

Tạo **`AnonymousReceiverTraceDemo.java`**:

```java
class Outer {
    private String text = "O";

    Runnable build() {
        return new Runnable() {
            private String text = "A";

            @Override
            public void run() {
                String local = "L";

                this.text = this.text + "1";
                Outer.this.text = Outer.this.text + "2";
                local = local + "3";

                System.out.println(local);
                System.out.println(this.text);
                System.out.println(Outer.this.text);
            }
        };
    }
}

public class AnonymousReceiverTraceDemo {
    public static void main(String[] args) {
        Runnable r = new Outer().build();
        r.run();
        r.run();
    }
}
```

```bash
javac AnonymousReceiverTraceDemo.java
java AnonymousReceiverTraceDemo
```

```text
L3
A1
O2
L3
A11
O22
```

**Tại sao?**

- `local` được tạo lại khi mỗi lần `run` bắt đầu, nên cả hai lần đều L3.
- Field `text` của anonymous object tồn tại qua hai lần gọi trên cùng Runnable, nên A→A1→A11.
- Field `text` của Outer instance cũng tồn tại và được sửa qua `Outer.this`, nên O→O2→O22.
- Anonymous receiver và Outer receiver **không bị gộp làm một** dù fields cùng tên.

Đây là một phép thử đơn giản phát hiện nhầm lẫn giữa local variable, anonymous field và outer field.

## 36. Checklist khi review `this` trong lớp vô danh

- [ ] Tôi đã xác định đúng **instance method/initializer** đang chứa biểu thức `this`?
- [ ] Tôi biết `this` trỏ anonymous object, không tự trỏ Outer?
- [ ] Tôi đã xác định lexical enclosing class và instance context?
- [ ] Có `Outer.this` hợp lệ tại vị trí code hay đang trong static method?
- [ ] Nếu anonymous nằm trong Inner, có cần `Inner.this` thay vì `Outer.this`?
- [ ] Có nhiều fields hoặc methods cùng tên ở anonymous/Inner/Outer không?
- [ ] Đã dùng `this.name` cho anonymous field và `Outer.this.name` cho outer field khi cần?
- [ ] Có parameter/local variable che field cùng tên không?
- [ ] Có đang dùng `super.member` để chỉ superclass chứ không nhầm outer?
- [ ] Nếu refactor anonymous thành lambda, nghĩa `this` có thay đổi không?
- [ ] Nếu lambda nằm trong anonymous method, lexical `this` là object nào?
- [ ] Nếu callback được return/lưu lại, enclosing Outer có thể bị giữ reachable quá lâu không?
- [ ] Có cần unregister event listeners ở cuối lifecycle không?
- [ ] Local captured variables có final/effectively final?
- [ ] Mutable captured references có aliasing ngoài ý muốn không?
- [ ] Nếu callback chạy nhiều threads, updates có thread-safe theo contract không?
- [ ] Có dùng class name compiler-generated để nhận diện anonymous object không? Nên tránh.
- [ ] Có đang gọi method chỉ thuộc anonymous concrete type từ biến static type Runnable không?
- [ ] Nếu muốn gọi private Outer method, access theo nested-class rules có phù hợp không?
- [ ] Khi muốn ghi state Outer, có method mang ý nghĩa nghiệp vụ thay vì sửa field trực tiếp không?
- [ ] Các Java examples có public class/file name đúng, lệnh `javac`/`java` và stdout xác định?

## 37. Câu hỏi tự luyện có đáp án

**Câu 1.** Trong `new Runnable(){ public void run(){ ... } }`, `this` của `run` chỉ object nào?

**Đáp án:** Chính anonymous Runnable object.

**Câu 2.** `Outer.this` trong anonymous class tạo từ Outer instance method chỉ object nào?

**Đáp án:** Enclosing Outer instance tương ứng, không phải anonymous object.

**Câu 3.** Anonymous và Outer cùng có field `name`, muốn đọc Outer field viết gì?

**Đáp án:** `Outer.this.name` trong lexical instance context hợp lệ.

**Câu 4.** Nếu method anonymous có parameter `name` thì `name` không định danh trỏ đâu?

**Đáp án:** Trỏ parameter nếu đó là khai báo gần nhất phù hợp; dùng `this.name`/`Outer.this.name` để chỉ fields.

**Câu 5.** `this` của anonymous class có type `Runnable` không?

**Đáp án:** Static type thực tế là anonymous class type, và value tương thích `Runnable` vì class implements Runnable. Có thể truyền `this` cho method nhận Runnable.

**Câu 6.** `Outer.this` có tự tạo một Outer object mới không?

**Đáp án:** Không; nó là expression tham chiếu enclosing Outer instance.

**Câu 7.** Từ anonymous class tạo trong static method của Outer, `Outer.this` có hợp lệ không?

**Đáp án:** Không có implicit enclosing Outer instance; truyền reference tường minh nếu cần.

**Câu 8.** Trong cùng static context, `this` bên trong anonymous instance method có dùng được không?

**Đáp án:** Có; nó chỉ anonymous object, không chỉ Outer.

**Câu 9.** `Outer.this` khác `Outer.class` thế nào?

**Đáp án:** Đầu tiên là Outer instance; thứ hai là Class object đại diện type Outer.

**Câu 10.** `super` của anonymous class có phải enclosing Outer không?

**Đáp án:** Không; `super` liên quan superclass, còn Outer.this liên quan lexical enclosing instance.

**Câu 11.** Anonymous class có khai báo constructor bằng tên kiểu không?

**Đáp án:** Không vì không có tên class source-level; có thể dùng instance initializer và constructor invocation của superclass theo cú pháp được ngôn ngữ cho phép.

**Câu 12.** Trong lambda trực tiếp tại Outer instance method, `this` là gì?

**Đáp án:** Lexical Outer instance.

**Câu 13.** Trong lambda viết bên trong anonymous `run()`, `this` là gì?

**Đáp án:** Lexical anonymous instance của `run`.

**Câu 14.** Nếu anonymous class được tạo trong member inner class Middle, dùng gì để đọc Middle field?

**Đáp án:** `Middle.this.field` trong enclosing context hợp lệ.

**Câu 15.** Có thể viết `Anonymous.this` trong source không?

**Đáp án:** Không có tên source-level Anonymous cho anonymous class; dùng `this` hoặc captured self reference thích hợp.

**Câu 16.** Vì sao callback trả ra khỏi method vẫn đọc được `Outer.this`?

**Đáp án:** Callback còn reference tới enclosing Outer instance theo ngữ nghĩa và implementation cần thiết; scope của local variable không kết thúc runtime object.

**Câu 17.** Có thể dùng `Outer.this.method()` để gọi private Outer method không?

**Đáp án:** Có trong nested/anonymous context có quyền truy cập phù hợp theo Java access rules.

**Câu 18.** Captured local variable phải có thuộc tính gì?

**Đáp án:** Final hoặc effectively final theo Java rules.

**Câu 19.** Một captured StringBuilder có tự biến thành immutable không?

**Đáp án:** Không, capture reference không deep-copy hay đóng băng object.

**Câu 20.** Hai anonymous callbacks từ hai Outer objects khác nhau dùng `Outer.this` có nhất thiết cùng Outer không?

**Đáp án:** Không; mỗi callback tham chiếu enclosing Outer instance của lần tạo tương ứng.

**Câu 21.** Muốn nhận diện runtime anonymous class mà không dựa vào tên compiler sinh, có thể dùng API nào?

**Đáp án:** `object.getClass().isAnonymousClass()`, khi mục tiêu là nhận diện dạng runtime class.

**Câu 22.** Dùng `this.count++` trong anonymous class có tự tăng `Outer.this.count` không?

**Đáp án:** Không nếu anonymous và Outer có fields riêng cùng tên; phải chọn receiver đúng.

**Câu 23.** Anonymous class có thể giữ mutable state qua nhiều lần `run()` không?

**Đáp án:** Có; instance fields thuộc anonymous object còn tồn tại qua các lần gọi trên cùng instance.

**Câu 24.** Khi nào nên cân nhắc thay anonymous class bằng lambda?

**Đáp án:** Khi interface là functional interface và behavior đủ ngắn, không cần anonymous fields/initializer/receiver `this` đặc biệt; phải rà lại ngữ nghĩa `this` trước khi đổi.

**Câu 25.** Việc dùng `Outer.this` có tự bảo đảm thread safety không?

**Đáp án:** Không. Nó chỉ xác định receiver, không làm mutable operations atomic hoặc tạo đồng bộ.

---

**Ghi nhớ cuối bài:** **`this` trong lớp vô danh là chính anonymous object**. Nếu anonymous class được khai báo trong một **instance context của lớp bao ngoài**, **`Outer.this`** chỉ đúng enclosing Outer instance, còn `Inner.this` chỉ enclosing Inner instance ở tầng phù hợp. Phải phân biệt **trùng tên** ở local variable/anonymous field/outer field và **receiver** của method calls. **Lớp vô danh khác lambda:** lambda dùng lexical `this`, nên khi chuyển code từ anonymous sang lambda cần kiểm ngữ nghĩa thật sự. Trong **static context**, không có Outer instance ngầm để dùng `Outer.this`; hãy truyền owner reference tường minh. Và cuối cùng, callback lưu lâu có thể giữ enclosing instance reachable, nên cân nhắc lifecycle, captured references và synchronization khi thiết kế.