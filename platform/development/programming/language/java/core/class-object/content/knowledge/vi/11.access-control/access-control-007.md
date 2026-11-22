# Truy cập `private` giữa các lớp lồng trong cùng lớp bao trong Java

Trong Java, `private` thường được giải thích là “chỉ lớp khai báo mới truy cập được”. Cách nói này hữu ích lúc mới học nhưng **chưa đầy đủ khi có lớp lồng (nested class)**. Trong cùng một **lớp bao cấp cao nhất (top-level enclosing class)**, Java cho phép lớp bao và các lớp được khai báo lồng bên trong truy cập thành viên `private` của nhau theo quy tắc truy cập của ngôn ngữ. Quyền đó còn áp dụng cho những lớp lồng cùng cấp trong phạm vi chung, miễn biểu thức truy cập đúng kiểu, đúng ngữ cảnh instance/static.

Ví dụ, một lớp lồng có thể đọc trường `private` của lớp bao. Chiều ngược lại, lớp bao có thể gọi constructor `private` của lớp lồng và đọc trường `private` của một đối tượng lớp lồng. Hai lớp lồng cùng cấp cũng có thể truy cập thành viên `private` của nhau. **Không cần đổi `private` thành package-private hay `public` chỉ để các thành phần cùng một cấu trúc lớp bao cộng tác.**

Bài này thuộc Java Core — *class-object*, nhóm **Kiểm soát truy cập**. Các ví dụ dùng **Java 17+**, phân biệt `static nested class`, *inner class*, local/anonymous class, giới hạn đối với các lớp độc lập bên ngoài, cùng những nhầm lẫn liên quan `this` và cơ chế *nestmates*.

## 1. Ôn lại `private` và cấu trúc lớp lồng

Một **thành viên private** có thể là trường, phương thức, constructor, kiểu thành viên hoặc thành viên khác được Java cho phép khai báo `private`. `private` giới hạn truy cập từ mã không thuộc phạm vi được phép; nó **không có nghĩa** rằng mọi mã bên trong cấu trúc lồng đều bị chặn khỏi các thành viên riêng của nhau.

Mẫu cấu trúc:

~~~java
public class Container {
    private int secret = 10;

    private static class StaticHelper {
        private int helperCode = 5;
    }

    private class InnerHelper {
        private String label = "inside";
    }
}
~~~

Đoạn trên là một **lớp minh họa hợp lệ**, chưa có `main`. Ở đây:

- `Container` là lớp bao cấp cao nhất (*top-level class*).
- `StaticHelper` là **static nested class**: kiểu thành viên được khai báo `static`.
- `InnerHelper` là **non-static member class**, thường gọi ngắn là *inner class*.
- Cả hai kiểu thành viên được khai báo `private`; mã độc lập ở ngoài `Container` không thể tùy tiện viết `Container.StaticHelper` để sử dụng kiểu riêng này.
- Tuy nhiên, code bên trong `Container` và các lớp được lồng trong cấu trúc đó có thể truy cập những thành viên `private` thích hợp.

**Chú ý phạm vi:** “Cùng file `.java`” và “cùng package” **không phải** điều kiện mở quyền `private`. Quy tắc quan trọng là **quan hệ lớp bao/lớp lồng** trong cùng cấu trúc top-level, chứ không phải vị trí vật lý của tệp.

## 2. Quy tắc truy cập: trong cùng lớp bao cấp cao nhất

Đối với một thành viên `private` được khai báo trong lớp `C`, Java xét quyền truy cập trong phạm vi **lớp hoặc interface top-level bao quanh khai báo của `C`**, theo các quy tắc accessibility ở JLS §6.6.1.

Có thể nhớ bằng sơ đồ:

~~~text
Outer (top-level)
|
+-- private field / method của Outer
|
+-- private static class A
|     +-- private field / method của A
|
+-- private class B (inner)
|     +-- private field / method của B
|
+-- class C
      +-- code có thể truy cập private của A, B, Outer
          nếu có đối tượng/ngữ cảnh thích hợp

Mã thuộc top-level class Khac ở ngoài cấu trúc Outer
không có quyền riêng này chỉ vì cùng package hoặc cùng file.
~~~

Bốn hướng truy cập cần phân biệt:

| Hướng | Được Java cho phép? | Điều kiện thực tế |
| --- | --- | --- |
| Lớp lồng đọc `Outer.privateField` | Có | Phải có **đối tượng Outer** nếu đó là instance field |
| Lớp bao đọc `Nested.privateField` | Có | Phải có **đối tượng Nested** nếu đó là instance field |
| Lớp lồng `A` gọi `B.privateMethod()` | Có | Phải có instance của `B` nếu method không static |
| Lớp top-level độc lập đọc `Outer.privateField` | Không | Không tự được phép dù ở cùng package/file |

**Được phép truy cập** không có nghĩa là một biểu thức luôn biên dịch. Nếu trường là instance field, vẫn phải đáp ứng quy tắc có **receiver object**. Nếu thành viên không nằm trong phạm vi được truy cập theo kiểu biểu thức, compiler vẫn từ chối.

## 3. Ví dụ hoàn chỉnh: lớp bao, static nested và inner cộng tác

Tạo tệp **`PrivateNestDemo.java`**. Ví dụ này chứng minh cả ba chiều: lớp bao dùng private của lớp lồng; lớp lồng dùng private của lớp bao; hai lớp lồng dùng private của nhau.

~~~java
public class PrivateNestDemo {
    private static final String PREFIX = "NEST";
    private final String owner;
    private int score;

    private PrivateNestDemo(String owner, int score) {
        this.owner = owner;
        this.score = score;
    }

    private String summary() {
        return owner + ":" + score;
    }

    private static class Inspector {
        private final int offset;

        private Inspector(int offset) {
            this.offset = offset;
        }

        private String examine(PrivateNestDemo host) {
            return host.owner + ":" + (host.score + offset)
                    + ":" + PREFIX;
        }
    }

    private class Editor {
        private int setScore(int next) {
            if (next < 0) {
                throw new IllegalArgumentException("score âm");
            }
            PrivateNestDemo.this.score = next;
            return score;
        }

        private String detail() {
            return owner + "/" + score;
        }
    }

    private static class Peer {
        private int offsetOf(Inspector inspector) {
            return inspector.offset;
        }

        private int update(Editor editor) {
            return editor.setScore(23);
        }
    }

    public static void main(String[] args) {
        PrivateNestDemo host = new PrivateNestDemo("An", 10);
        Inspector inspector = new Inspector(4);
        PrivateNestDemo.Editor editor = host.new Editor();
        Peer peer = new Peer();

        System.out.println("outer=" + host.summary());
        System.out.println("inspector=" + inspector.examine(host));
        System.out.println("offset=" + peer.offsetOf(inspector));
        System.out.println("updated=" + peer.update(editor));
        System.out.println("outer now=" + host.summary());
        System.out.println("editor=" + editor.detail());
    }
}
~~~

Chạy từ thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 PrivateNestDemo.java
java PrivateNestDemo
~~~

**Stdout:**

~~~text
outer=An:10
inspector=An:14:NEST
offset=4
updated=23
outer now=An:23
editor=An/23
~~~

### Truy cập nào đặc biệt trong ví dụ này?

1. `PrivateNestDemo` tự gọi constructor `private PrivateNestDemo(...)` và method `private summary()`.
2. `main`, dù được khai báo trong lớp bao, vẫn có thể tạo `new Inspector(4)`, **gọi constructor private** của lớp `Inspector`.
3. `Inspector.examine(host)` là phương thức **private của Inspector**. Lớp bao gọi nó hợp lệ vì thuộc cùng cấu trúc lồng.
4. Bên trong `Inspector.examine`, code đọc **`host.owner` và `host.score`**, dù đó là hai field `private` của lớp bao. `Inspector` là lớp lồng tĩnh nên nhận rõ tham chiếu `host` để đọc instance field.
5. `Inspector` đọc trực tiếp `PREFIX` là **private static field** của lớp bao; thành viên static không đòi một object Outer.
6. `Peer.offsetOf(inspector)` đọc **`inspector.offset`**, một field private của **lớp lồng cùng cấp `Inspector`**.
7. `Peer.update(editor)` gọi **`Editor.setScore(23)`**, một phương thức private của lớp lồng cùng cấp `Editor`.
8. `Editor.setScore` viết `PrivateNestDemo.this.score`, tức field của **outer instance đang bao quanh Editor**. `editor` liên kết với `host` do biểu thức `host.new Editor()`.
9. Sau khi `Editor` cập nhật field, `host.summary()` nhìn được `score=23` vì cả hai làm việc trên **cùng một outer object**.

Điểm cốt lõi: không có thao tác nào phải nới quyền sang `public`. Việc gọi được là vì **cùng phạm vi lớp bao**, đồng thời những chỗ truy cập instance field đều có receiver thích hợp.

## 4. Chiều thứ nhất: lớp lồng truy cập `private` của lớp bao

Trong chương trình `PrivateNestDemo`, có hai kiểu truy cập rất khác:

~~~java
private String examine(PrivateNestDemo host) {
    return host.owner + ":" + (host.score + offset)
            + ":" + PREFIX;
}
~~~

Đây là trích đoạn **phương thức của static nested class `Inspector`**, không phải một tệp độc lập. Nó truy cập:

- `host.owner`, `host.score`: **instance fields private** của một object `PrivateNestDemo`.
- `PREFIX`: **static field private** của lớp bao.
- `offset`: instance field private của `Inspector` hiện tại.

Vì `Inspector` là **static nested class**, nó **không có một outer instance ngầm định**. Do đó:

~~~java
private int read(PrivateNestDemo host) {
    return host.score;
}
~~~

là cách hợp lệ để đọc instance field private của một `host` được truyền vào. Nhưng viết `return score;` ngay trong static nested class mà **không có đối tượng Outer để chọn field** không tự hợp lệ chỉ vì lớp đó lồng trong `PrivateNestDemo`.

**Quy tắc ghi nhớ:** `private` quyết định *ai được quyền đọc*; `static` và cơ chế receiver quyết định *đọc từ object nào*.

## 5. Chiều thứ hai: lớp bao truy cập `private` của lớp lồng

Cũng trong cùng chương trình:

~~~java
Inspector inspector = new Inspector(4);
System.out.println(inspector.examine(host));
~~~

Cả constructor `Inspector(int)` lẫn `Inspector.examine(PrivateNestDemo)` đều là **private**, nhưng đoạn mã trong lớp bao có quyền dùng.

Để hiểu chính xác, hãy phân biệt:

- **Quyền nhìn thấy kiểu** `Inspector`: kiểu được khai báo là member private trong `PrivateNestDemo`.
- **Quyền gọi constructor** `Inspector(int)`: constructor cũng private.
- **Quyền gọi phương thức** `examine(...)`: method private.
- **Khả năng cung cấp tham số hợp lệ**: lời gọi cần một `PrivateNestDemo host`.

Việc lớp bao đọc một **instance field của lớp lồng** cũng yêu cầu có object lớp lồng: `inspector.offset`, không phải cố đọc `Inspector.offset` bởi `offset` không static.

Sự phối hợp này hữu ích khi một cấu trúc lớn cần nhiều helper nội bộ nhưng **không muốn công khai chi tiết triển khai** ra package hoặc API public.

## 6. Chiều thứ ba: hai lớp lồng cùng cấp đọc `private` của nhau

Trong ví dụ:

~~~java
private static class Peer {
    private int offsetOf(Inspector inspector) {
        return inspector.offset;
    }

    private int update(Editor editor) {
        return editor.setScore(23);
    }
}
~~~

Đoạn trên là định nghĩa **lớp lồng `Peer`** trích từ chương trình hoàn chỉnh. `Peer` không phải superclass hay subclass của `Inspector` hoặc `Editor`. Ba lớp lồng là **các kiểu thành viên cùng thuộc một top-level `PrivateNestDemo`**.

Điều này đủ để code của `Peer` truy cập những thành viên private của `Inspector` và `Editor`, miễn có object hợp lệ để gọi method hoặc đọc field.

**Không cần quan hệ kế thừa** để được phép truy cập private trong cùng nest. Cũng không phải `private` trở thành `public`: lớp độc lập ở ngoài `PrivateNestDemo` vẫn không có đặc quyền ấy.

Nếu kiểu `Inspector` được khai báo `private`, lớp ngoài cũng không thể tùy ý nêu tên `PrivateNestDemo.Inspector`; đó là một giới hạn khác biệt với quyền truy cập nội bộ đã thấy.

## 7. Static nested class và inner class khác nhau ở outer instance

Hai khai báo:

~~~java
class Outer {
    private int value = 10;

    static class StaticReader {
        int read(Outer target) {
            return target.value;
        }
    }

    class InnerReader {
        int read() {
            return value;
        }
    }
}
~~~

Đây là một **lớp minh họa hợp lệ**. Cả `StaticReader` và `InnerReader` đều truy cập `Outer.value` dù đó là private. Nhưng cách lấy object khác nhau:

| Khía cạnh | `static class StaticReader` | `class InnerReader` |
| --- | --- | --- |
| Có outer instance ngầm định? | Không | Có, đối với non-static member inner class |
| Cách truy cập `private static` của Outer | `Outer.staticField` hoặc tên đơn giản hợp lệ | Tương tự |
| Cách truy cập `private int value` | `target.value` với `Outer target` | Có thể viết `value` hoặc `Outer.this.value` |
| Cách tạo từ một method static khác | `new Outer.StaticReader()` nếu truy cập kiểu được | `outer.new InnerReader()`, cần outer instance |
| `this` trong phương thức của lớp lồng | Object `StaticReader` | Object `InnerReader` |
| `Outer.this` có dùng được? | Không có enclosing Outer instance | Có trong ngữ cảnh inner thích hợp |

Tính `static` **không hủy quyền private** giữa hai kiểu lồng trong một top-level. Nó chủ yếu quyết định **có một instance của lớp bao gắn kèm hay không**.

Đừng nhầm `Outer.this` với `this`: bên trong `InnerReader`, `this` là **inner object**, còn `Outer.this` là **outer object** bao quanh nó.

## 8. Ví dụ chạy được về `Outer.this` và tên field bị che

Một inner class có thể tự khai báo một field trùng tên với field của Outer. Khi đó `this.value` và `Outer.this.value` cho hai giá trị khác nhau.

Tạo tệp **`OuterThisPrivateDemo.java`**:

~~~java
public class OuterThisPrivateDemo {
    private final int value = 10;

    private class Inner {
        private final int value = 3;

        private int sum() {
            return this.value + OuterThisPrivateDemo.this.value;
        }

        private String detail() {
            return "inner=" + this.value
                    + ",outer=" + OuterThisPrivateDemo.this.value;
        }
    }

    private static class StaticReader {
        private int read(OuterThisPrivateDemo target) {
            return target.value;
        }
    }

    public static void main(String[] args) {
        OuterThisPrivateDemo outer = new OuterThisPrivateDemo();
        Inner inner = outer.new Inner();
        StaticReader reader = new StaticReader();

        System.out.println(inner.detail());
        System.out.println("sum=" + inner.sum());
        System.out.println("static=" + reader.read(outer));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 OuterThisPrivateDemo.java
java OuterThisPrivateDemo
~~~

**Stdout:**

~~~text
inner=3,outer=10
sum=13
static=10
~~~

`Inner.sum()` lấy field `value=3` của **chính inner object**, cộng với field `value=10` của **outer object**. `StaticReader.read(outer)` không dùng `OuterThisPrivateDemo.this`; nó phải nhận `outer` làm đối số.

Nếu chỉ viết `value` trong `Inner`, tên field của inner che field cùng tên ở Outer. Để truy cập field của Outer khi bị che khuất, viết rõ `OuterThisPrivateDemo.this.value`.

## 9. Lớp cục bộ và lớp vô danh cũng có thể truy cập private

Nested class không chỉ gồm member class. Java còn có **local class** khai báo trong một khối và **anonymous class** được tạo bằng biểu thức lớp vô danh. Chúng cũng có thể sử dụng thành viên private của ngữ cảnh bao quanh khi quy tắc scope/receiver cho phép.

Tạo tệp **`LocalAnonymousPrivateDemo.java`**:

~~~java
public class LocalAnonymousPrivateDemo {
    private final int secret = 7;

    private int addSecret(int input) {
        return secret + input;
    }

    void demonstrate(int amount) {
        class LocalReader {
            int read() {
                return addSecret(amount);
            }
        }

        Runnable anonymous = new Runnable() {
            @Override
            public void run() {
                System.out.println("anonymous=" + secret);
            }
        };

        System.out.println("local=" + new LocalReader().read());
        anonymous.run();
    }

    public static void main(String[] args) {
        LocalAnonymousPrivateDemo owner =
                new LocalAnonymousPrivateDemo();
        owner.demonstrate(5);
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 LocalAnonymousPrivateDemo.java
java LocalAnonymousPrivateDemo
~~~

**Stdout:**

~~~text
local=12
anonymous=7
~~~

Giải thích:

- `LocalReader.read()` gọi **phương thức private `addSecret`** của outer instance, đồng thời sử dụng tham số `amount` của phương thức bao quanh.
- `anonymous.run()` đọc **private field `secret`** của outer instance.
- `amount` được **bắt giữ (captured)** bởi local class nên phải là `final` hoặc *effectively final*. Ở đây không có phép gán lại `amount`, nên hợp lệ.
- Cả local class và anonymous class ở ví dụ nằm trong **instance method**, nên có một outer instance để truy cập.

Trong **static method**, local/anonymous class không tự nhiên nhận outer instance chỉ vì tồn tại một lớp bao. Muốn đọc instance field private của Outer trong bối cảnh static, phải có một tham chiếu Outer hợp lệ.

**Không gộp hai quy tắc:** quyền truy cập private của nest không tự loại bỏ điều kiện *effectively final* đối với biến cục bộ được capture.

## 10. Ranh giới: cùng tệp Java không đồng nghĩa cùng nest

Có thể khai báo **nhiều top-level class** trong cùng một tệp nguồn (với các giới hạn về `public`). Nhưng chúng là **các lớp độc lập**, không vì cùng file mà nhận đặc quyền truy cập private của nhau.

Tạo tệp **`PrivateBoundaryDemo.java`**:

~~~java
class Vault {
    private final int code = 19;

    private static class Reader {
        private int read(Vault vault) {
            return vault.code;
        }
    }

    static int readThroughOwnNested(Vault vault) {
        return new Reader().read(vault);
    }
}

class Neighbor {
    int askThroughAllowedApi(Vault vault) {
        return Vault.readThroughOwnNested(vault);
    }

    // Không được dùng vault.code: code là private của Vault.
    // Không được dùng kiểu Vault.Reader: Reader là private của Vault.
}

public class PrivateBoundaryDemo {
    public static void main(String[] args) {
        Vault vault = new Vault();
        Neighbor neighbor = new Neighbor();
        System.out.println(neighbor.askThroughAllowedApi(vault));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 PrivateBoundaryDemo.java
java PrivateBoundaryDemo
~~~

Stdout:

~~~text
19
~~~

Trong ví dụ:

- `Reader` là **lớp lồng của Vault**, nên `Reader.read(vault)` được phép đọc `vault.code` private.
- `Vault` được phép gọi constructor private của `Reader` (constructor mặc định sinh ra từ class private này có mức truy cập cùng lớp theo quy tắc) và phương thức `Reader.read` private.
- `Neighbor` là **top-level class khác** dù nằm cùng tệp. Nó không được đọc `vault.code` hoặc dùng kiểu `Vault.Reader`.
- `Neighbor` gọi `Vault.readThroughOwnNested`, một **phương thức package-private** được thiết kế làm cổng truy cập có kiểm soát cho ví dụ.
- `PrivateBoundaryDemo` chỉ làm việc qua API được `Neighbor` cung cấp.

Ví dụ có đủ code để **biên dịch và chạy**; các thao tác không hợp lệ được ghi bằng lời trong comment, không phải các lời gọi thực thi.

Quy tắc tương tự đối với **cùng package**: `package-private` có thể cho truy cập trong package; `private` không tự mở quyền cho mọi class của package.

## 11. `private` trên kiểu lồng khác gì `private` trên field?

Cả hai cùng dùng `private` nhưng kiểm soát các việc khác nhau:

~~~java
class Outer {
    private static class Engine {
        private int capacity = 8;
    }

    private final Engine engine = new Engine();

    int capacity() {
        return engine.capacity;
    }
}
~~~

Đây là một **lớp minh họa hợp lệ**.

- `private static class Engine` hạn chế những nơi có thể **nêu tên kiểu `Engine`**.
- `private int capacity` hạn chế những nơi được **truy cập field `capacity`**.
- `private final Engine engine` hạn chế những nơi được **truy cập field `engine` của Outer**.
- `Outer.capacity()` là method package-private có thể cung cấp **một thông tin được phép công bố**, mà không lộ trực tiếp object Engine.

Không phải vì lớp ngoài được dùng `engine.capacity` mà mọi caller của `Outer` cũng được phép gọi `engine.capacity` trực tiếp.

**Thực hành thiết kế:** một lớp lồng `private` thích hợp cho helper là chi tiết triển khai nội bộ. Nó giảm API public của lớp bao, nhưng vẫn cho các phần trong cùng cấu trúc sử dụng thành viên riêng khi cần.

## 12. Vì sao Java cho phép kiểu lồng truy cập private của nhau?

Lớp bao và các lớp lồng thường là **một đơn vị thiết kế**. Ví dụ một cấu trúc dữ liệu có thể có:

- `Outer`: API được công bố.
- `Node`: cấu trúc nút nội bộ, gồm trường `private`.
- `IteratorImpl`: lớp lồng duyệt các nút.
- `Validator`: lớp lồng kiểm tra invariant.

Nếu mọi helper nội bộ phải công bố field chỉ để một helper khác sử dụng, API sẽ bị nới rộng không cần thiết. Java cho phép các kiểu này cộng tác mà **không mở quyền private ra top-level class độc lập**.

Tuy nhiên, khả năng truy cập không phải là lý do để một helper tùy ý sửa mọi trạng thái:

- Nếu một field phải luôn dương, code của lớp lồng khác vẫn có thể phá invariant nếu gán trực tiếp một giá trị sai.
- Nên đặt các thay đổi phức tạp qua method kiểm tra dữ liệu, dù code nội bộ có quyền private.
- Một cấu trúc lồng quá lớn, nhiều lớp phụ thuộc chéo vào private field của nhau, có thể gây khó bảo trì.
- Đừng hiểu `private` là một biện pháp an toàn tuyệt đối trước reflection, instrumentation hoặc các cơ chế có đặc quyền khác; đây là **kiểm soát truy cập ngôn ngữ** cho code thông thường.

Có thể xem quyền private trong nest là **quyền cộng tác nội bộ**, không phải giấy phép bỏ qua các quy tắc thiết kế của lớp.

## 13. Cơ chế compile/runtime: nestmates trong Java hiện đại

Ở mức source, Java đã cho phép các cấu trúc lồng thích hợp truy cập private của nhau từ lâu. Điều thú vị là các nested class vẫn thường được biên dịch thành **những class file riêng**, chẳng hạn:

~~~text
PrivateNestDemo.class
PrivateNestDemo$Inspector.class
PrivateNestDemo$Editor.class
PrivateNestDemo$Peer.class
~~~

Những tên tệp trên là **cấu trúc class file thường thấy sau javac**, không phải cú pháp tên lớp trong source. Tên nhị phân của member class dùng ký tự `$` theo quy tắc đặt tên Java.

### Java 8 và trước: có thể thấy accessor do compiler tạo

Trước Java 11, các JVM đời cũ không có cùng cơ chế runtime nestmate như hiện nay. Compiler thường tạo những **synthetic accessor** trong bytecode để triển khai quyền truy cập private của lớp lồng, trong khi chương trình nguồn vẫn hợp lệ. Đây là chi tiết triển khai của compiler, không phải một phương thức mà lập trình viên cần tự định nghĩa.

### Java 11 trở đi: nest-based access control

Từ Java 11, JVM hỗ trợ **nestmates**. Các class file trong cùng nest có thể mô tả mối liên hệ thông qua metadata như `NestHost` và `NestMembers`, để JVM kiểm tra quyền private giữa nestmates. Vì vậy với `javac` hiện đại, những trường hợp truy cập private giữa lớp bao/lồng có thể được biểu diễn trực tiếp trong bytecode mà không cần các synthetic accessor như trước.

Có thể tự quan sát bằng các lệnh sau sau khi đã biên dịch tệp ở mục 3:

~~~bash
javap -p PrivateNestDemo
javap -v -p PrivateNestDemo
javap -v -p 'PrivateNestDemo$Inspector'
~~~

Cú pháp quote của shell có thể thay đổi giữa PowerShell, CMD và Unix shell, nên dòng cuối cần điều chỉnh cách escape/quote ký tự `$` cho môi trường thực tế. Trên shell PowerShell, dùng dấu nháy đơn như ví dụ để tránh nội suy `$`.

Kết quả `javap` rất dài và phụ thuộc phiên bản compiler; do đó không đưa một stdout giả định cố định. Hãy tìm các thông tin `NestMembers`, `NestHost`, tên các field private và lệnh truy cập trong bản class file do `javac` tạo.

**Ý quan trọng nhất:** nestmate là **cơ chế JVM hỗ trợ cho quyền truy cập private**, không phải một modifier mới trong source và cũng **không biến private thành package-private**. Hai top-level class độc lập ở cùng package không thành nestmates chỉ vì cùng tên thư mục hoặc cùng tệp Java.

## 14. Quyền truy cập và quan hệ kế thừa không phải một

Lớp con bình thường **không kế thừa quyền sử dụng trực tiếp một private member** của lớp cha chỉ vì quan hệ `extends`. Một lớp lồng có thể truy cập private của outer **vì phạm vi lồng**, không phải vì nó kế thừa outer.

Ví dụ minh họa:

~~~java
class Parent {
    private int secret = 7;

    int readSecret() {
        return secret;
    }
}

class Child extends Parent {
    int readViaApi() {
        return readSecret();
    }

    // Không thể truy cập trực tiếp secret chỉ vì Child extends Parent.
}
~~~

Đây là đoạn khai báo hợp lệ, không có `main`. `Child.readViaApi()` gọi một method package-private của `Parent` (trong cùng package), nhưng không được đọc trực tiếp field `secret` private theo tư cách subclass độc lập.

Nếu thiết kế cần subclass dùng một thành viên, hãy cân nhắc **phương thức protected/public phù hợp** và bảo toàn invariant; không vội chuyển field thành `protected`. Với nested class, dùng `private` vẫn thường là lựa chọn tốt vì sự cộng tác diễn ra trong cùng cấu trúc top-level.

## 15. Nhầm lẫn về `this` và receiver khi truy cập private

Một lỗi rất phổ biến là suy luận “được truy cập private” thành “có thể viết tên field trần ở bất kỳ đâu”. Cần đọc đúng ngữ cảnh:

| Biểu thức | Khi nào hợp lệ? | Ý nghĩa |
| --- | --- | --- |
| `outer.secret` | Code có quyền private và `outer` là một object Outer thích hợp | Đọc field của `outer` |
| `Outer.this.secret` | Đang ở ngữ cảnh có **enclosing Outer instance** | Đọc field của outer object bao quanh |
| `secret` trong non-static inner class | Nếu phân giải tên tìm thấy field outer và không bị che | Đọc field qua outer instance ngầm định |
| `secret` trong static nested class | Chỉ khi tên phù hợp ngữ cảnh, thường không thể dùng instance field outer như vậy | Không tự có outer instance |
| `nested.privateMethod()` | Có quyền private và `nested` là receiver tương thích | Gọi instance method private |
| `Nested.privateStaticMethod()` | Có quyền private và method thực sự static | Gọi method qua tên kiểu |

Trong một **inner class**, `this` là **đối tượng inner**. Nếu muốn outer instance, dùng `Outer.this` khi hợp lệ. Trong một **static nested class**, không có `Outer.this` vì không có enclosing Outer instance ngầm định.

Khi truy cập field private của một lớp lồng khác, **không thể chỉ viết `fieldName` để đọc instance field của object kia** nếu không có quan hệ tên/receiver tương ứng; hãy dùng một đối tượng như `peer.fieldName`.

## 16. Những trường hợp bị từ chối hoặc dễ hiểu sai

| Trường hợp | Có vấn đề gì? | Cách tiếp cận đúng |
| --- | --- | --- |
| `private` top-level class | Top-level class thông thường không được khai báo `private` | Dùng top-level class có mức truy cập hợp lệ hoặc nested private class |
| Hai top-level class cùng `.java` dùng private của nhau | Cùng tệp không tạo quyền private | Cung cấp API phù hợp hoặc đặt helper thực sự lồng nhau |
| Hai class cùng package truy cập private | Private không phải package-private | Dùng member mức package-private chỉ khi chủ đích |
| Static nested class viết `Outer.this.field` | Không có outer instance ngầm định | Truyền object Outer, viết `outer.field` |
| Static nested class đọc instance field Outer bằng tên trần | Không có receiver Outer để đọc | Dùng `outer.field` |
| Outer đọc instance field của nested bằng `Nested.field` | Field không static | Tạo/nhận object nested rồi `nested.field` |
| Inner class dùng `this.field` và nghĩ là field Outer | `this` trỏ inner object | `Outer.this.field` nếu đang có outer instance |
| Lớp lồng đọc local bị gán lại sau khi capture | Local/parameter capture phải final hoặc effectively final | Giữ biến không gán lại hoặc sao chép giá trị phù hợp |
| Chuyển mọi private field thành public cho nested truy cập | Phá giới hạn API không cần thiết | Giữ private, dùng quyền trong nest |
| Nghĩ mọi subclass có quyền như nested class | Kế thừa không tự cấp quyền truy cập private | Phân biệt nesting với inheritance |
| Thấy class file riêng nên tưởng không được truy cập private | Java/JVM có cơ chế hỗ trợ truy cập giữa nestmates | Phân biệt source access rule với bytecode representation |
| Các lớp lồng dùng được private nên field khỏi cần validation | Mọi code có quyền vẫn có thể phá invariant | Kiểm tra dữ liệu và tổ chức API nội bộ rõ |

Một chương trình chỉ đọc field bên trong nested class khác có thể biên dịch hợp lệ, nhưng **đúng quyền truy cập không bảo đảm đúng nghiệp vụ**. Nếu hai lớp lồng có trách nhiệm riêng, ưu tiên phương thức ý nghĩa rõ hơn việc chỉnh trực tiếp các field then chốt.

## 17. Quy trình rà soát khi compiler báo lỗi truy cập

Khi gặp thông báo như *has private access*, *not an enclosing class* hoặc *non-static variable cannot be referenced from a static context*, hãy xác định:

1. **Ai khai báo thành viên?** Ví dụ `Outer.secret` hay `Outer.Inner.code`.
2. **Code đang truy cập nằm ở đâu?** Trong cùng top-level enclosing class, trong lớp lồng cùng nest, hay trong top-level class độc lập?
3. **Thành viên là static hay instance?** Nếu instance, cần một receiver phù hợp.
4. **Lớp lồng là static hay non-static?** Có outer instance ngầm định hay không?
5. **Có shadowing tên không?** `this.field` có thể là field inner, `Outer.this.field` mới là field outer.
6. **Có đang dùng kiểu private từ bên ngoài không?** Có thể cần public/package-visible API của lớp bao thay vì lộ kiểu private.
7. **Có nhầm inheritance với nesting không?** Subclass độc lập không nhận quyền private của superclass.
8. **Có capture biến cục bộ không?** Local/anonymous class cần biến được capture final/effectively final.
9. **Nếu source đã đúng, có vấn đề cấu hình bytecode/module/class loader không?** Đây là nhánh nâng cao cần kiểm tra riêng, không nên tùy tiện sửa tất cả field thành public.

Các bước này giúp tìm **đúng loại lỗi**: thiếu quyền, thiếu đối tượng, sai phạm vi static, che tên, hoặc kiểu không nhìn thấy.

## 18. Bài tập thực hành

**Bài 1 — Phân quyền.** Với `Outer` chứa `private int secret` và `private static class Reader`, method `Reader.read(Outer outer)` có thể `return outer.secret;` không? Vì sao?

**Bài 2 — Chiều ngược.** `Outer` có thể gọi một method `private int read()` của object `Reader` không? Khi nào phải dùng `reader.read()` thay vì `Reader.read()`?

**Bài 3 — Cùng cấp.** `Outer.A` và `Outer.B` là hai member nested class cùng cấp, không kế thừa nhau. Nếu `A` có private field `code`, code trong `B` có thể đọc `a.code` khi có instance `A a` không?

**Bài 4 — Static nested.** Vì sao `Outer.StaticReader` không thể dùng `Outer.this.secret`? Viết cách đọc thay thế nếu method nhận `Outer target`.

**Bài 5 — Inner và shadowing.** Outer có `private int value=10`; Inner có `private int value=3`. Trong một instance method của Inner, `this.value` và `Outer.this.value` là bao nhiêu?

**Bài 6 — Cùng file.** Hai top-level class `A` và `B` được khai báo trong một file. `B` có được gọi `A.privateMethod()` chỉ vì cùng file không? Đề xuất một cách công bố hành vi cần thiết mà không công khai field.

**Bài 7 — Capture.** Trong instance method của Outer, một local class đọc private field `secret` và local variable `int extra=5`. Sau khi tạo local class, có thể gán lại `extra=6` nếu local class đã capture `extra` không?

**Bài 8 — Quy tắc ngữ cảnh.** Cho `Outer` chứa một field instance `private String name`. Một static nested class có method `String describe(Outer owner)`. Hãy viết câu lệnh trả về `name` của `owner` và giải thích tại sao method ấy vẫn truy cập được private.

**Bài 9 — Nestmates.** Vì sao `javac` có thể xuất nhiều class file riêng cho Outer và Inner nhưng source vẫn được phép truy cập private qua lại? Nêu tên cơ chế JVM hiện đại hỗ trợ.

**Bài 10 — Thiết kế.** Một iterator được khai báo là nested class của một collection. Nó có quyền ghi trực tiếp các private field của collection. Điều gì nên hạn chế việc ghi ấy dù compiler cho phép?

### Đáp án tham khảo

1. Có. `Reader` nằm trong cùng top-level Outer, và `outer` là receiver rõ ràng cho instance field private.
2. Có, nếu trong cùng nest và có object `reader`; `read()` là instance method nên phải gọi `reader.read()` thay vì qua tên class.
3. Có. Hai lớp nằm trong cùng nest; `a.code` sử dụng receiver instance thích hợp.
4. Static nested không có enclosing Outer instance; dùng `return target.secret;` với đối số `target` hợp lệ.
5. Lần lượt là 3 và 10, giả định đang ở Inner gắn với một outer object có field `value=10`.
6. Không. Nên cung cấp một phương thức có quyền truy cập cần thiết trên `A`, hoặc tổ chức một helper lồng đúng chỗ khi phù hợp.
7. Không. Biến được local class capture phải final/effectively final; việc gán lại `extra` phá điều kiện này.
8. `return owner.name;`. Static nested được quyền private do nesting, nhưng cần `owner` làm receiver cho instance field.
9. Trình biên dịch biểu diễn nested class bằng class file riêng; Java 11+ hỗ trợ **nest-based access control/nestmates** ở JVM, và các compiler cũ từng sử dụng synthetic accessor.
10. Phải giữ invariant của collection, cập nhật các thông tin nhất quán và tránh phá hợp đồng iterator; quyền private không thay thế kiểm tra/thiết kế trách nhiệm.

## 19. Tài liệu đối chiếu

- [Java Language Specification 17, §6.6 — Access Control](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6): quy tắc kiểm soát quyền truy cập.
- [Java Language Specification 17, §6.6.1 — Determining Accessibility](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6.1): phạm vi cho phép đối với private member và constructor.
- [Java Language Specification 17, §8.1.3 — Inner Classes and Enclosing Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.3): inner class và enclosing instance.
- [Java Language Specification 17, §15.8.3 — `this`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.8.3): biểu thức `this` và qualified `Outer.this`.
- [Java Virtual Machine Specification 17, §5.4.4 — Access Control](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.4): nestmates và kiểm tra private access lúc liên kết/chạy.
- [Java SE 17 — javap](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): quan sát khai báo/member và metadata trong class file.

**Ghi nhớ:** `private` không đóng kín hoàn toàn giữa những lớp **thuộc cùng cấu trúc top-level enclosing class**. Outer, inner, static nested, các lớp lồng cùng cấp và lớp cục bộ/vô danh thích hợp có thể truy cập private của nhau theo quy tắc Java. Nhưng quyền truy cập **không tự sinh receiver object**, **không biến instance field thành static**, và **không mở quyền cho mọi class cùng package hoặc cùng file**. Luôn phân biệt phạm vi private với ngữ cảnh `this`/`Outer.this`, và giữ invariant dù code nội bộ có thể truy cập trực tiếp.
