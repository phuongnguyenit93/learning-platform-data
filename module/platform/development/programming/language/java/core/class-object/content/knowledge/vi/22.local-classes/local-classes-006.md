# Giới hạn từ khóa truy cập và `static` trên lớp cục bộ thông thường trong Java 17

**Lớp cục bộ thông thường** (*local normal class*) là một lớp có tên được khai báo trực tiếp trong một block, chẳng hạn thân method, constructor hoặc initializer. Điểm đặc biệt của lớp này là **nó không phải thành viên (member) của lớp bao ngoài**. Vì thế không thể dùng quy tắc modifier của member class để áp cho dòng khai báo local class.

Hai câu dễ bị nhầm phải được tách riêng:

1. **Trên chính khai báo local normal class**: không được viết `public`, `protected`, `private`, `static`, `sealed` hoặc `non-sealed`.
2. **Trong phần thân local normal class ở Java 17**: vẫn có thể khai báo **static fields, static methods, static initializer blocks và static nested member types** theo quy tắc phù hợp. Điều này **khác với hạn chế của các Java versions trước Java 16**.

Ví dụ hợp lệ trong Java 17:

```java
void demonstrate() {
    int offset = 2;

    final class Local {
        static int base() {
            return 10;
        }

        int calculate() {
            return base() + offset;
        }
    }

    System.out.println(new Local().calculate());
}
```

Đây là **đoạn method**, chưa phải một source file chạy độc lập. `final` đặt trên khai báo local class hợp lệ. `static` đặt trên **method `base` bên trong Local** cũng hợp lệ ở Java 17. Nhưng đổi dòng `final class Local` thành `static class Local` là **lỗi biên dịch**.

Bài hướng dẫn giải thích modifier ở cấp **class declaration** so với modifier ở cấp **member declaration**, quy định theo Java Language Specification (JLS), những trường hợp hợp lệ/bị từ chối, local enum/record/interface, static context, captured variables, access scope, cách chạy `javac --release 17`, nhiều ví dụ có stdout xác định, bài tập và checklist.

## 1. Xác định đúng “local normal class”

Ví dụ:

```java
class Host {
    void process() {
        class LocalWorker {
            void execute() {
                System.out.println("working");
            }
        }

        new LocalWorker().execute();
    }
}
```

`LocalWorker` là **local normal class** vì khai báo `class LocalWorker` được chứa trực tiếp trong block của `process()`. Nó không phải một field, method, member class hay top-level class.

So sánh:

```java
class Host {
    // Đây là member nested class:
    private static class MemberHelper {
    }

    void process() {
        // Đây mới là local normal class:
        class LocalHelper {
        }
    }
}
```

`MemberHelper` được khai báo **trong body của Host**, tại vị trí khai báo member. `LocalHelper` được khai báo **trong block của method**. Sự khác biệt về vị trí kéo theo các quy định modifier khác nhau.

### “Thông thường” nghĩa là gì?

Trong JLS 17 `14.3, local class có thể là:
- **Local normal class**: khai báo bằng từ khóa `class`; thông thường đây là một **inner class**.
- **Local enum class**: khai báo `enum` trong block, **implicitly static**.
- **Local record class**: khai báo `record` trong block, **implicitly static**.

JLS 17 còn cho phép **local interface** trong block, cũng **implicitly static**. Các loại enum/record/interface có quy tắc khác local **normal** class, vì vậy không gộp tất cả vào một kết luận “local class luôn là inner”.

## 2. Bảng modifier cần ghi nhớ

Xét **modifier viết ngay trước `class Local`**, không phải modifiers của các method/field nằm bên trong.

| Modifier ở khai báo local normal class | Java 17 | Ghi chú |
| --- | --- | --- |
| Không có modifier | Hợp lệ | Mặc định thường gặp |
| `final` | Hợp lệ | Cấm subclass của local class |
| `abstract` | Hợp lệ | Không thể trực tiếp `new Local()` |
| `strictfp` | Cú pháp được phép | Trong Java 17, strict floating-point mặc định khiến modifier này không còn tác dụng thực tế |
| Annotation phù hợp `@...` | Hợp lệ theo target | Ví dụ annotation có `@Target(TYPE)` |
| `public` | **Không hợp lệ** | Local class không phải public member/top-level |
| `protected` | **Không hợp lệ** | Không có member access modifier ở khai báo local class |
| `private` | **Không hợp lệ** | Phạm vi tên do lexical block quyết định |
| `static` | **Không hợp lệ** | Local normal class không được ghi `static` trong khai báo |
| `sealed` | **Không hợp lệ** | JLS `14.3 cấm |
| `non-sealed` | **Không hợp lệ** | JLS `14.3 cấm |
| `abstract final` cùng lúc | **Không hợp lệ** | Hai ràng buộc trái nhau |

**Không suy ra:** “local normal class không được có static member”. Đó là **câu hỏi khác** và trong Java 17 có đáp án khác.

## 3. Vì sao `public`, `protected`, `private` bị cấm?

Các access modifiers của **class declaration** mang ý nghĩa quản lý khả năng truy cập của:
- Top-level class: `public` hoặc package-private.
- Member class: `public`, `protected`, `private` hoặc package-private.
- Local class: **không có ba access modifiers trên**.

Tên local class đã được giới hạn bởi **lexical scope của block** và không trở thành một member type có thể truy cập bằng cú pháp như `Host.Local`.

Ví dụ sai:

```java
void run() {
    private class Local {
    }
}
```

Đoạn này **cố ý không biên dịch**: `private` không được dùng trước local class declaration. Bỏ `private`:

```java
void run() {
    class Local {
    }
    Local value = new Local();
}
```

Người viết có thể nghĩ “mình muốn giới hạn Local trong method nên khai báo private”, nhưng chính việc đặt khai báo trong method đã giới hạn **phạm vi tên local class**. Thêm `private` không làm class “riêng tư hơn”; nó chỉ gây lỗi biên dịch.

### `protected` cũng không tạo khả năng mở rộng

Không được dùng `protected class Local` với hy vọng subclass từ package khác sẽ nhìn thấy local class. Local type không phải protected member. Nếu cần một type được kế thừa/truy cập như member từ nơi khác, thiết kế **member nested class hoặc top-level class** phù hợp.

## 4. Runnable: local class hợp lệ không có access modifier

Lưu **`LocalModifierBasics.java`**:

```java
public class LocalModifierBasics {
    static void execute() {
        class Counter {
            private int value;

            Counter(int initial) {
                value = initial;
            }

            int next() {
                return ++value;
            }
        }

        Counter counter = new Counter(3);
        System.out.println(counter.next());
        System.out.println(counter.next());
    }

    public static void main(String[] args) {
        execute();
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 LocalModifierBasics.java
java LocalModifierBasics
```

**Stdout:**

```text
4
5
```

Lưu ý phân biệt:
- `class Counter` **không có** `private` trước từ khóa class.
- `private int value` **ở bên trong Counter** là một field declaration hợp lệ.
- Constructor và instance method của Counter hoạt động như trên một class thông thường.
- Tên `Counter` được dùng trong `execute()`, không được dùng như một member type `LocalModifierBasics.Counter` ở bên ngoài method.

## 5. Giới hạn access modifier của *class* khác quyền truy cập của *member*

Một local normal class vẫn có thể chứa fields/methods với các access modifiers hợp lệ của chính những members đó.

```java
void process() {
    class Local {
        private int hidden = 1;

        public int read() {
            return hidden;
        }

        protected void update(int value) {
            hidden = value;
        }
    }

    Local local = new Local();
    local.update(7);
    System.out.println(local.read());
}
```

Đây là snippet trong body method. Khai báo `Local` **không có access modifier**, nhưng `hidden` là private field; `read` public method; `update` protected method.

Java không áp quy tắc “local class cấm public” lên **mọi method bên trong**. Quy tắc cấm đang xét là **modifier trên dòng khai báo local class hoặc interface**.

### Có nên viết public methods bên trong local class?

Có thể hợp lệ về cú pháp; nhưng tên type `Local` không công bố ra ngoài scope. Một public method có ích khi instance được trả ra qua một interface/superclass mà method ấy override hoặc khi code hợp lệ bên trong phạm vi cần dùng.

Modifier `public` trên method **không biến `Local` thành public top-level type**. Hãy xét API thật sự mà caller thấy.

## 6. Runnable: members của local class có access modifiers

Lưu **`LocalMemberAccessDemo.java`**:

```java
public class LocalMemberAccessDemo {
    interface Reader {
        int read();
    }

    static Reader make() {
        class LocalReader implements Reader {
            private int value = 7;

            public int read() {
                return value;
            }

            private void set(int next) {
                value = next;
            }

            LocalReader() {
                set(9);
            }
        }

        return new LocalReader();
    }

    public static void main(String[] args) {
        Reader reader = make();
        System.out.println(reader.read());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 LocalMemberAccessDemo.java
java LocalMemberAccessDemo
```

**Stdout:**

```text
9
```

`LocalReader` không mang access modifier của **class declaration**, còn member method `read` được khai báo public để triển khai `Reader.read()`, vốn mặc nhiên public.

`LocalReader` được trả ra bằng interface `Reader`. Caller chỉ cần `reader.read()`, không cần nhìn thấy tên `LocalReader` ở ngoài `make()`.

## 7. `final` trên local normal class

Cú pháp:

```java
void process() {
    final class Local {
        String name() {
            return "local";
        }
    }
}
```

**Hợp lệ.** `final` cấm lớp khác kế thừa `Local`, giống với final top-level/member classes.

Nó **không**:
- Làm các instance fields của Local tự động bất biến;
- Cấm tạo nhiều Local objects;
- Biến Local thành static;
- Mở rộng scope của tên Local.

### Runnable: final local class

Lưu **`FinalLocalDemo.java`**:

```java
public class FinalLocalDemo {
    public static void main(String[] args) {
        final class LocalMessage {
            private String text;

            LocalMessage(String text) {
                this.text = text;
            }

            String get() {
                return text;
            }
        }

        LocalMessage first = new LocalMessage("A");
        LocalMessage second = new LocalMessage("B");

        System.out.println(first.get());
        System.out.println(second.get());
        System.out.println(first == second);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 FinalLocalDemo.java
java FinalLocalDemo
```

Stdout:

```text
A
B
false
```

`final` ở class declaration giới hạn kế thừa; field `text` vẫn là một field bình thường có thể mutable trong các methods có quyền truy cập. Đây không phải một ví dụ bất biến sâu.

## 8. `abstract` trên local normal class

Java 17 cho phép:

```java
void process() {
    abstract class LocalBase {
        abstract String describe();
    }

    class LocalImpl extends LocalBase {
        @Override
        String describe() {
            return "implemented";
        }
    }

    LocalBase item = new LocalImpl();
}
```

`LocalBase` có tên trong method, được dùng làm superclass của local implementation. **Không được tạo bằng `new LocalBase()`** vì abstract class là incomplete.

### Vì sao không đặt cả `abstract` và `final`?

`abstract` biểu thị class chưa hoàn tất, cần subclass concrete để tạo đối tượng; `final` lại ngăn subclass. Hai ràng buộc trên cùng một class là lỗi compile-time.

**Phân biệt:** `abstract`/`final` được phép **riêng rẽ** ở khai báo local normal class; không phải mọi tổ hợp hai modifiers hợp lệ riêng lẻ đều hợp lệ chung.

## 9. Runnable: abstract local class có implementation cục bộ

Lưu **`AbstractLocalDemo.java`**:

```java
public class AbstractLocalDemo {
    static String describe(int number) {
        abstract class LocalBase {
            abstract String render();
        }

        final class Decimal extends LocalBase {
            @Override
            String render() {
                return "number=" + number;
            }
        }

        LocalBase value = new Decimal();
        return value.render();
    }

    public static void main(String[] args) {
        System.out.println(describe(7));
        System.out.println(describe(10));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AbstractLocalDemo.java
java AbstractLocalDemo
```

**Stdout:**

```text
number=7
number=10
```

Method parameter `number` được capture trong instance method của local subclass và **effectively final** vì không bị gán lại.

Không nhầm vấn đề capture này với tính hợp lệ của modifier `abstract` hoặc `final` trên hai local class declarations.

## 10. `static class Local`: không hợp lệ

Ví dụ sai:

```java
void run() {
    static class Local {
    }
}
```

Đây là **ví dụ compile-negative có chủ đích**. `static` không được đặt **trước khai báo** local normal class.

Một lý do khái niệm: modifier `static` trên khai báo **member nested class** phân biệt member type có/không có implicit enclosing instance, còn local class **không phải member class**.

Ví dụ hợp lệ khác:

```java
class Outer {
    static class MemberNested {
    }
}
```

Ở đây `MemberNested` nằm trực tiếp trong body Outer, nên `static` hợp lệ. Nó **không phải local class**.

### Vẫn có local class trong static method

`static` của **enclosing method** khác với `static` trên **declaration của local class**:

```java
static void work() {
    class Local {
    }
}
```

Code hợp lệ: local class được khai báo **bên trong static context**. Điều này không tự cấp enclosing Outer instance.

Hai phát biểu sau không đồng nghĩa:
- “Một local class được khai báo **trong static method**.” → Có thể hợp lệ.
- “Local class tự được khai báo **`static class`**.” → Bị cấm ở `14.3`.

## 11. Runnable: local class bên trong static method

Lưu **`StaticMethodLocalDemo.java`**:

```java
public class StaticMethodLocalDemo {
    private static final String PREFIX = "S-";

    static String create(int id) {
        class Local {
            String value() {
                return PREFIX + id;
            }
        }

        return new Local().value();
    }

    public static void main(String[] args) {
        System.out.println(create(3));
        System.out.println(create(8));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 StaticMethodLocalDemo.java
java StaticMethodLocalDemo
```

Stdout:

```text
S-3
S-8
```

`Local` không có `static` trước `class`. Nó vẫn được khai báo trong `static String create(...)`, dùng static field `PREFIX` và capture parameter `id` effectively final.

### Không có `Outer.this` trong static context

Nếu `create` cần một instance field `ownerName`, phải có **explicit owner reference** hoặc chuyển code sang instance method. Việc khai báo local class không làm static method có `this`.

## 12. Cột mốc Java 16: thay đổi hạn chế static members

Đây là kiến thức rất quan trọng khi đọc mã nhiều phiên bản:

**Trước Java SE 16**, inner classes có quy tắc chặt hơn: nhìn chung không được khai báo static initializer hoặc static members, trừ các **constant variables** theo định nghĩa JLS.

**Từ Java SE 16 và trong Java SE 17**, hạn chế ấy đã được nới. JLS `8.1.3 cho phép **inner class khai báo và kế thừa static members, có static initializer**, dù bản thân nó vẫn là inner class.

Do đó trong Java 17:

```java
void process() {
    class Local {
        static int counter = 1;

        static int next() {
            return ++counter;
        }

        static {
            System.out.println("Local initialized");
        }
    }

    System.out.println(Local.next());
}
```

Đây là snippet body method **hợp lệ khi biên dịch với Java 17**. Dòng `class Local` không có modifier static, nhưng **members bên trong** có modifier static.

### So sánh hai cấp độ

| Nơi viết `static` | Ví dụ | Java 17 |
| --- | --- | --- |
| Trước local normal class declaration | `static class Local {}` trong method | **Lỗi** |
| Trước field của local normal class | `class Local { static int n; }` | **Hợp lệ** |
| Trước method của local normal class | `class Local { static void run(){} }` | **Hợp lệ** |
| Static initializer của local normal class | `class Local { static { ... } }` | **Hợp lệ** |
| Trước member class nằm trong local class body | `class Local { static class Nested{} }` | **Hợp lệ** |
| Local record/enum/interface declaration ghi `static` rõ ràng | `static record R(int x) {}` trong block | **Lỗi** |
| Local record/enum/interface không ghi `static` | `record R(int x) {}` trong block | **Hợp lệ; implicitly static** |

**Đây là sự phân biệt không thể thay bằng khẩu quyết “local class cấm static”**.

## 13. Runnable: static field và static method trong local class Java 17

Lưu **`LocalStaticMembersDemo.java`**:

```java
public class LocalStaticMembersDemo {
    static void demonstrate() {
        class LocalCounter {
            private static int count = 1;

            static int next() {
                return ++count;
            }

            int snapshot() {
                return count;
            }
        }

        LocalCounter counter = new LocalCounter();

        System.out.println(LocalCounter.next());
        System.out.println(counter.snapshot());
        System.out.println(LocalCounter.next());
    }

    public static void main(String[] args) {
        demonstrate();
    }
}
```

```bash
javac --release 17 -encoding UTF-8 LocalStaticMembersDemo.java
java LocalStaticMembersDemo
```

**Stdout:**

```text
2
2
3
```

**Giải thích:**
- `LocalCounter` là **local normal class** trong static method.
- `count` là static field **của chính LocalCounter type**, không phải instance field của `counter`.
- `next()` là static method của LocalCounter.
- `snapshot()` là instance method được gọi trên LocalCounter object.
- Class vẫn là **local** do nơi khai báo, không trở thành member nested class chỉ vì có static members.

### Cẩn thận khi so với Java 8

Lấy một project cũ đang compile bằng `--release 8` rồi đưa code có static nonconstant fields/methods trong local class vào có thể gây lỗi compile. Khi hướng dẫn Java 17, dùng đúng **language level** của bài chứ không áp rập khuôn giới hạn lịch sử.

## 14. Runnable: static initializer trong local normal class

Lưu **`LocalStaticInitializerDemo.java`**:

```java
public class LocalStaticInitializerDemo {
    static void demonstrate() {
        class LocalConfig {
            static final int VALUE;

            static {
                VALUE = 17;
                System.out.println("initializing LocalConfig");
            }

            static int version() {
                return VALUE;
            }
        }

        System.out.println(LocalConfig.version());
        System.out.println(LocalConfig.version());
    }

    public static void main(String[] args) {
        demonstrate();
    }
}
```

```bash
javac --release 17 -encoding UTF-8 LocalStaticInitializerDemo.java
java LocalStaticInitializerDemo
```

**Stdout:**

```text
initializing LocalConfig
17
17
```

Static initializer chạy khi JVM khởi tạo `LocalConfig` type theo quy tắc class initialization, không phải mỗi lần gọi `version()`.

`VALUE` là static final field được gán trong static initializer. Nó không phải *compile-time constant variable* vì không có constant expression initializer tại khai báo.

Đây là **khả năng hợp lệ ở Java 17** cần phân biệt với quy tắc cũ trước Java 16.

## 15. Static context bên trong local class vẫn bị hạn chế

“Cho phép static members” **không** có nghĩa static method tự truy cập được mọi biến đang bao quanh local class.

Xét snippet:

```java
void process() {
    int offset = 5;

    class Local {
        static int calculate() {
            // return offset; // Không hợp lệ.
            return 10;
        }

        int calculateWithOffset() {
            return calculate() + offset;
        }
    }
}
```

`offset` là một local variable ở **method bao ngoài**. Instance method `calculateWithOffset()` của Local có thể capture `offset` nếu effectively final. Nhưng static method `calculate()` của Local **không được capture local variable từ enclosing method qua ranh giới static context**.

Tương tự static method:
- Không có `this` của Local object.
- Không có implicit enclosing instance được cung cấp qua nó.
- Không dùng instance members trần nếu không có receiver thích hợp.
- Không được dùng `Outer.this` chỉ nhờ lexical nesting khi đang trong static context ấy.

### Cách sửa

Truyền giá trị vào static method:

```java
class Local {
    static int calculate(int offset) {
        return 10 + offset;
    }
}

System.out.println(Local.calculate(offset));
```

Đây là một snippet trong block. Nó thể hiện dependency tường minh. Hoặc nếu behavior thực sự cần captured instance state, đưa logic vào **instance method** của local class.

## 16. Runnable: cùng một local class có static và instance method

Lưu **`StaticBoundaryDemo.java`**:

```java
public class StaticBoundaryDemo {
    static int compute(int input) {
        int bonus = 3;

        class Local {
            static int doubleValue(int value) {
                return value * 2;
            }

            int result() {
                return doubleValue(input) + bonus;
            }
        }

        return new Local().result();
    }

    public static void main(String[] args) {
        System.out.println(compute(4));
        System.out.println(compute(10));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 StaticBoundaryDemo.java
java StaticBoundaryDemo
```

**Stdout:**

```text
11
23
```

`doubleValue` chỉ sử dụng parameter của **chính static method đó**, không capture `input` hay `bonus` từ outer method. Instance method `result` được phép capture `input` và `bonus`.

Đây là sự phân tách **scope và receiver**, không phải lệnh cấm toàn bộ static members.

## 17. Static member type bên trong local class

Trong Java 17, một local normal class có thể chứa một **static nested member class**.

Snippet:

```java
void demonstrate() {
    class Local {
        static class Detail {
            static String label() {
                return "detail";
            }
        }
    }

    System.out.println(Local.Detail.label());
}
```

`Detail` là member class của `Local`, còn `Local` là local class của block. Không có `static` trước `class Local`.

### Runnable

Lưu **`LocalNestedTypeDemo.java`**:

```java
public class LocalNestedTypeDemo {
    static void execute() {
        class Local {
            static class Detail {
                static String label() {
                    return "detail";
                }
            }

            String instanceLabel() {
                return Detail.label() + "-instance";
            }
        }

        System.out.println(Local.Detail.label());
        System.out.println(new Local().instanceLabel());
    }

    public static void main(String[] args) {
        execute();
    }
}
```

```bash
javac --release 17 -encoding UTF-8 LocalNestedTypeDemo.java
java LocalNestedTypeDemo
```

Stdout:

```text
detail
detail-instance
```

Dùng `Local.Detail` chỉ **trong scope nơi tên Local còn nhìn thấy**. Từ method khác không thể tự viết `Local.Detail` như thể Local là public member type của enclosing top-level class.

## 18. Local interface, record và enum: cùng vị trí block, quy tắc khác

Java 17 cho phép các declarations trong block:

```java
void run() {
    interface Rule {
        boolean accepts(int value);
    }

    record Pair(int left, int right) {
    }

    enum Mode {
        FAST, SAFE
    }
}
```

Chúng có **tên cục bộ**, nhưng:
- Local interface **implicitly static**.
- Local record **implicitly static**.
- Local enum **implicitly static**.

Vì vậy **không có implicit enclosing instance** theo cách local normal inner class có thể có trong instance context. Chúng không capture enclosing local variables hay Outer instance state theo cơ chế instance của local normal class.

**Không viết `static interface Rule`, `static record Pair` hoặc `static enum Mode` trong block**. Modifier static rõ ràng bị `14.3` cấm trên local declarations, mặc dù chúng có static semantics **mặc nhiên**.

### Local interface không phải annotation interface

JLS 17 cho phép normal local interface declaration, nhưng **không cho một annotation interface** ở dạng local interface. Không gộp `@interface` vào cùng một rule với local normal interface.

## 19. Runnable: local interface, record, enum

Lưu **`LocalStaticKindsDemo.java`**:

```java
public class LocalStaticKindsDemo {
    static void demonstrate() {
        interface Rule {
            boolean accepts(int value);
        }

        record Pair(int left, int right) {
            int sum() {
                return left + right;
            }
        }

        enum Mode {
            FAST, SAFE
        }

        Rule positive = value -> value > 0;
        Pair pair = new Pair(3, 4);
        Mode mode = Mode.SAFE;

        System.out.println(positive.accepts(3));
        System.out.println(pair.sum());
        System.out.println(mode);
    }

    public static void main(String[] args) {
        demonstrate();
    }
}
```

```bash
javac --release 17 -encoding UTF-8 LocalStaticKindsDemo.java
java LocalStaticKindsDemo
```

**Stdout:**

```text
true
7
SAFE
```

Ví dụ không truyền dữ liệu enclosing method cho các types implicitly static. `Rule`, `Pair`, `Mode` chỉ có tên trong scope method.

**Quan trọng:** điều kiện `public/private/protected/static/sealed/non-sealed` trên **khai báo local type** áp dụng theo `14.3`; đừng lấy quy tắc riêng của member record/interface rồi đặt nguyên modifier vào local declaration.

## 20. Local record không capture biến local method

Xét snippet:

```java
void run() {
    int offset = 5;

    record Pair(int left, int right) {
        int sum() {
            return left + right;
            // return left + right + offset; // Không hợp lệ.
        }
    }
}
```

`Pair` là **local record**, implicitly static nên method instance của Pair không được capture `offset` từ outer method theo cách instance method của local normal class có thể.

Nếu cần `offset`, đưa nó vào:
- Record component;
- Parameter method;
- Explicit dependency/constructor field được phép;
- Hoặc thiết kế một local normal class nếu enclosing capture là chủ đích.

### Runnable: truyền state qua record component

Lưu **`LocalRecordCaptureDemo.java`**:

```java
public class LocalRecordCaptureDemo {
    static int calculate(int value) {
        int offset = 5;

        record ValueWithOffset(int value, int offset) {
            int total() {
                return value + offset;
            }
        }

        ValueWithOffset item =
                new ValueWithOffset(value, offset);

        return item.total();
    }

    public static void main(String[] args) {
        System.out.println(calculate(3));
        System.out.println(calculate(10));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 LocalRecordCaptureDemo.java
java LocalRecordCaptureDemo
```

Stdout:

```text
8
15
```

Record không capture `offset` một cách ngầm định; caller **truyền offset tường minh** vào component khi tạo record instance.

## 21. Biến local được capture bởi normal local class

Một local normal class có thể đọc biến cục bộ hoặc parameter từ enclosing method khi thỏa:
- Biến được khai báo và nằm trong scope hợp lệ.
- Biến đã definitely assigned khi được sử dụng.
- Biến là **final hoặc effectively final**.
- Việc sử dụng không bị cấm bởi static context khác.

Ví dụ:

```java
void execute() {
    int threshold = 10;

    class Checker {
        boolean accepts(int value) {
            return value > threshold;
        }
    }

    System.out.println(new Checker().accepts(12));
}
```

`threshold` được gán một lần, nên effectively final.

### Ví dụ sai do gán lại

```java
void execute() {
    int threshold = 10;

    class Checker {
        boolean accepts(int value) {
            return value > threshold;
        }
    }

    threshold = 20; // Không còn effectively final.
}
```

Trình biên dịch từ chối sử dụng `threshold` trong local class vì local variable được capture không effectively final. Điều này **khác** lỗi access modifier và **khác** lỗi ghi `static class Local`.

## 22. Runnable: local class capture parameter effectively final

Lưu **`EffectivelyFinalLocalDemo.java`**:

```java
public class EffectivelyFinalLocalDemo {
    static String formatter(String prefix, int id) {
        String suffix = "!";

        class LocalFormatter {
            String format() {
                return prefix + "-" + id + suffix;
            }
        }

        return new LocalFormatter().format();
    }

    public static void main(String[] args) {
        System.out.println(formatter("A", 3));
        System.out.println(formatter("B", 7));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EffectivelyFinalLocalDemo.java
java EffectivelyFinalLocalDemo
```

Stdout:

```text
A-3!
B-7!
```

`prefix` và `id` là method parameters; `suffix` là local variable. Không biến nào bị gán lại nên chúng đều effectively final.

### Capture reference không đồng nghĩa immutable object

Nếu một effectively-final local variable chứa `List` hoặc array reference, local class vẫn có thể quan sát mutations của referent qua alias. Quy tắc effectively final áp dụng cho **gán lại biến**, không tự tạo deep copy hay thread-safety.

## 23. Local normal class trong instance context

Một local normal class khai báo trong **instance method** có thể truy cập state của enclosing object trong ngữ cảnh hợp lệ.

```java
class CounterHost {
    private int base = 10;

    int calculate(int value) {
        class Local {
            int result() {
                return base + value;
            }
        }

        return new Local().result();
    }
}
```

`base` được đọc từ enclosing `CounterHost` instance; `value` được capture từ method parameter effectively final.

Nếu chuyển `calculate` thành static method rồi vẫn đọc `base` trực tiếp, sẽ không có `CounterHost.this` trong static context.

**Chữ “local class” không tự quyết định có enclosing instance**: phải biết **nó được khai báo trong instance hay static context**.

## 24. Runnable: instance context và `Outer.this`

Lưu **`LocalOuterContextDemo.java`**:

```java
public class LocalOuterContextDemo {
    private final String name;

    LocalOuterContextDemo(String name) {
        this.name = name;
    }

    String describe(int id) {
        class Local {
            String label() {
                return LocalOuterContextDemo.this.name + "#" + id;
            }
        }

        return new Local().label();
    }

    public static void main(String[] args) {
        LocalOuterContextDemo a =
                new LocalOuterContextDemo("A");
        LocalOuterContextDemo b =
                new LocalOuterContextDemo("B");

        System.out.println(a.describe(1));
        System.out.println(b.describe(2));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 LocalOuterContextDemo.java
java LocalOuterContextDemo
```

Stdout:

```text
A#1
B#2
```

Ở đây `LocalOuterContextDemo.this` hợp lệ vì local class nằm trong một instance method context phù hợp. Điều này **không** biến Local thành member class; nó vẫn là local normal class.

## 25. Static method của Local không có `Outer.this`

Trong **static member** của một local class, không có receiver `this`, và không thể dựa vào enclosing instance/local captures.

Ví dụ cố ý sai:

```java
class Outer {
    private int base = 10;

    void method() {
        class Local {
            static int read() {
                // return Outer.this.base; // Lỗi static context.
                return 0;
            }
        }
    }
}
```

Dù local class được khai báo trong Outer instance method, `read()` là static method **bên trong Local**. Cần một explicit `Outer` object, parameter hoặc một instance method của Local có access hợp lệ.

Phân biệt:
- Instance method của local normal class có thể tham chiếu enclosing context phù hợp.
- Static method của local normal class vẫn tuân thủ **quy tắc static context**.

### Giải pháp truyền receiver

```java
class Local {
    static int read(Outer owner) {
        return owner.base;
    }
}
```

Đây là snippet trong scope có type Outer và access hợp lệ. Nó **không capture** Outer instance; receiver được cung cấp tường minh.

## 26. `strictfp`: hợp lệ nhưng không nên lạm dụng

`strictfp` từng được dùng để yêu cầu strict floating-point semantics. Với Java 17, Java áp dụng **always-strict floating-point semantics** theo cập nhật của ngôn ngữ; dùng `strictfp` thường không thêm tác dụng và có thể tạo cảnh báo từ compiler.

Ví dụ cú pháp:

```java
void run() {
    strictfp class Local {
        double half(double value) {
            return value / 2.0;
        }
    }
}
```

Đây là snippet body method. **Không nên dùng strictfp để “sửa” lỗi access/static modifiers**: nó thuộc vấn đề floating-point semantics, không liên quan visibility hoặc enclosing instance.

Chỉ cần ghi nhớ `strictfp` vẫn có mặt trong danh sách class modifiers của JLS 17, nhưng **không còn là cách hữu ích để thay đổi precision của phép tính** trong Java 17.

## 27. Annotation trên local normal class

Một annotation áp dụng cho **type declaration** có thể được viết trước local normal class nếu `@Target` của annotation cho phép.

Ví dụ:

```java
void work() {
    @Deprecated
    class LocalOld {
        String value() {
            return "old";
        }
    }

    LocalOld value = new LocalOld();
}
```

`@Deprecated` ở đây là một **annotation**, không phải access modifier. Nó không công bố class ra ngoài scope.

Không phải mọi annotation đều được phép gắn vào mọi chỗ: Java kiểm tra `@Target`, applicability và retention. Ví dụ annotation chỉ dành cho FIELD không thể được áp dụng tùy tiện lên khai báo local class.

### Runnable: annotation type target

Lưu **`AnnotatedLocalDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@interface Marker {
}

public class AnnotatedLocalDemo {
    static String read() {
        @Marker
        class Local {
            String value() {
                return "marked";
            }
        }

        return new Local().value();
    }

    public static void main(String[] args) {
        System.out.println(read());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AnnotatedLocalDemo.java
java AnnotatedLocalDemo
```

Stdout:

```text
marked
```

Annotation có target TYPE phù hợp; code không giả định annotation xuất hiện qua Reflection vì không khai báo runtime retention. Việc khai báo annotation trên local class **không thay thế access modifier**.

## 28. `sealed` và `non-sealed`: vì sao không được đặt trên local declaration?

Java 17 có sealed classes để giới hạn direct subclasses. Nhưng **JLS `14.3 cấm `sealed` và `non-sealed` trên local class/interface declarations**.

Ví dụ sai:

```java
void work() {
    sealed class Local permits Child {
    }

    final class Child extends Local {
    }
}
```

Đây là **mã cố ý không biên dịch**, bất kể cố khai báo permitted subclass. Lý do đầu tiên là modifier `sealed` không hợp lệ trên local class declaration.

Một local normal class cũng **không được trực tiếp extends một sealed class hoặc implements một sealed interface** theo điều kiện đặc biệt của JLS 14.3. Điều này giúp tách local declarations khỏi mô hình permitted subclasses của sealed hierarchy.

### Hướng thiết kế thay thế

- Nếu cần một sealed hierarchy public hoặc private member rõ ràng, khai báo hierarchy ở **top-level hoặc member level** phù hợp.
- Nếu chỉ cần hai implementations trong method, có thể dùng abstract local base class cộng local concrete subclasses, nhưng **không dùng sealed modifier**.
- Nếu yêu cầu closed set đơn giản của values, cân nhắc local enum hoặc nested enum tùy scope, không ép sealed local class.

## 29. So sánh local class, member inner và static nested

Đây là bảng chống nhầm lẫn khi code review:

| Ví dụ | Là loại gì? | Access trên khai báo? | `static` trên khai báo? |
| --- | --- | --- | --- |
| `class Host { private class Inner {} }` | Member inner | `private` hợp lệ | Không được dùng đồng thời để vẫn là inner |
| `class Host { private static class Helper {} }` | Static nested member | `private` hợp lệ | Hợp lệ |
| `void m() { class Local {} }` | Local normal | Không dùng public/protected/private | Không được |
| `static void m() { class Local {} }` | Local normal trong static context | Không dùng access modifiers | Không được |
| `void m() { final class Local {} }` | Final local normal | `final` hợp lệ | Không được |
| `void m() { abstract class Local {} }` | Abstract local normal | `abstract` hợp lệ | Không được |
| `void m() { record R(int x) {} }` | Local record | Không dùng access modifiers | Implicitly static, không ghi `static` |
| `void m() { interface I {} }` | Local interface | Không dùng access modifiers | Implicitly static, không ghi `static` |

**Quyết định từ vị trí khai báo.** Cùng tên `Helper` nhưng nằm ở class body hay method block là hai trường hợp khác nhau.

## 30. Scope của tên lớp cục bộ

Một local class có **tên trong phạm vi cục bộ**. Để dùng kiểu `Local`, code phải nằm trong scope nơi tên này nhìn thấy theo quy tắc lexical scope.

Ví dụ:

```java
void process() {
    class Local {
    }

    Local here = new Local();
}

void other() {
    // Local there = new Local(); // Không thấy tên Local.
}
```

Dù class file cho local class có thể được compiler tạo ra, tên `Local` trong source code **không trở thành một member `Outer.Local`**.

### Local class có thể được trả về không?

Có, qua interface/superclass có visibility thích hợp:

```java
Runnable buildTask() {
    class LocalTask implements Runnable {
        @Override
        public void run() {
            System.out.println("done");
        }
    }

    return new LocalTask();
}
```

Caller giữ `Runnable` và gọi `run()` sau khi method return; **runtime object vẫn sống** nếu còn reachable, dù tên local class không nhìn thấy ngoài block.

## 31. Runnable: trả instance local class qua interface

Lưu **`LocalReturnScopeDemo.java`**:

```java
public class LocalReturnScopeDemo {
    static Runnable makeTask(String message) {
        class LocalTask implements Runnable {
            @Override
            public void run() {
                System.out.println(message);
            }
        }

        return new LocalTask();
    }

    public static void main(String[] args) {
        Runnable first = makeTask("first");
        Runnable second = makeTask("second");

        first.run();
        second.run();
    }
}
```

```bash
javac --release 17 -encoding UTF-8 LocalReturnScopeDemo.java
java LocalReturnScopeDemo
```

Stdout:

```text
first
second
```

`message` được capture vì effectively final. `main` không cần và không thể nhắc tên `LocalTask` trong source scope của nó.

### Vì sao không thêm `public class LocalTask`?

Thêm `public` trước local class declaration **không công bố type**; nó chỉ tạo lỗi compile. Muốn API reusable có tên, chuyển type sang member class hoặc top-level class đúng chỗ.

## 32. Local class trong constructor và initializer blocks

Không chỉ methods mới có block cho local class declaration. Một constructor hoặc initializer block có thể chứa local class hợp lệ.

Ví dụ constructor snippet:

```java
class Service {
    private final String name;

    Service(String source) {
        class Normalizer {
            String normalize() {
                return source.trim();
            }
        }

        name = new Normalizer().normalize();
    }
}
```

`Normalizer` chỉ có scope trong constructor block và capture `source` effectively final.

**Không nhầm với member class:** dù class xuất hiện trong source body của Service, nó vẫn nằm **bên trong constructor block**, vì thế không được dùng `private class Normalizer` hay `static class Normalizer`.

### Runnable

Lưu **`ConstructorLocalDemo.java`**:

```java
public class ConstructorLocalDemo {
    private final String name;

    ConstructorLocalDemo(String source) {
        class Normalizer {
            String normalize() {
                return source.trim().toUpperCase(
                        java.util.Locale.ROOT);
            }
        }

        name = new Normalizer().normalize();
    }

    public static void main(String[] args) {
        ConstructorLocalDemo value =
                new ConstructorLocalDemo(" java ");

        System.out.println(value.name);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ConstructorLocalDemo.java
java ConstructorLocalDemo
```

Stdout:

```text
JAVA
```

Trong snippet, `source` được capture hợp lệ và local class chỉ phục vụ quá trình tạo state cho constructor.

## 33. Reflection: `isLocalClass` không dựa vào modifier `static`

Một local normal class có thể được phân loại bằng `Class.isLocalClass()`.

Nếu class có static method/field trong Java 17, nó **vẫn là local class**. Modifier `static` của member field/method không khiến `Class.getModifiers()` của local type báo đó là một static nested member class.

Các methods hữu ích:
- `Class.isLocalClass()`: có phải local class không.
- `Class.isMemberClass()`: có phải member class không.
- `Class.isAnonymousClass()`: có phải anonymous class không.
- `Class.getEnclosingMethod()`/`getEnclosingConstructor()`: thông tin lexical enclosing context khi có.
- `Modifier.isStatic(clazz.getModifiers())`: modifier ở **class level**, không phải static members của class ấy.

### Runnable

Lưu **`LocalReflectionDemo.java`**:

```java
import java.lang.reflect.Modifier;

public class LocalReflectionDemo {
    static void inspect() {
        final class Local {
            static int number() {
                return 7;
            }
        }

        Class<?> type = Local.class;

        System.out.println(type.isLocalClass());
        System.out.println(type.isMemberClass());
        System.out.println(Modifier.isStatic(type.getModifiers()));
        System.out.println(Local.number());
    }

    public static void main(String[] args) {
        inspect();
    }
}
```

```bash
javac --release 17 -encoding UTF-8 LocalReflectionDemo.java
java LocalReflectionDemo
```

**Stdout:**

```text
true
false
false
7
```

`Local.number()` là static method nhưng **Local itself không được khai báo static**. Đó chính là sự phân biệt Java 17 cần hiểu.

Không in `type.getName()` thành expected fixed value, vì generated binary names của local classes phụ thuộc compiler/toolchain details.

## 34. Khác biệt khi `javac` chạy với `--release`

Chạy:

```bash
javac --release 17 -encoding UTF-8 LocalStaticMembersDemo.java
```

yêu cầu ngữ pháp và APIs phù hợp **Java 17**.

Trong một project vẫn xây bằng mức source cũ, ví dụ Java 8, code có static method/nonconstant static field bên trong local normal class sẽ không được chấp nhận theo quy tắc nguồn cũ.

**`--release` không chỉ là JVM runtime version**: nó hướng compiler chọn language/API compatibility của release đích.

### Bẫy thường gặp

- IDE dùng JDK 21 nhưng project source language level 8: code Java 17 vẫn có thể bị IDE/compiler từ chối.
- Maven/Gradle cấu hình `release = 8` dù máy cài JDK mới: ví dụ Java 17 trong bài sẽ không hợp lệ với cấu hình đó.
- Copy ví dụ từ Java 8 về giới hạn static members rồi kết luận “Java 17 cũng cấm”: không đúng.
- Cố chữa lỗi bằng cách ghi `static class Local`: vẫn sai cả trên Java 17.

**Khi chẩn đoán lỗi, hãy đọc cả vị trí `static` và release target.**

## 35. Không nên dùng static members local class chỉ vì ngôn ngữ cho phép

Trong Java 17, cú pháp sau hợp lệ:

```java
void run() {
    class Local {
        static int total;
    }
}
```

Nhưng về thiết kế:
- Static mutable state có lifetime/class-loading khác một call stack frame.
- Một method được gọi nhiều lần **không tạo một class type mới riêng cho từng lời gọi** theo semantics kiểu Java class declaration.
- Static field không tự là “biến cục bộ mỗi lần method chạy”.
- Mutable static fields có thể cần synchronization nếu dùng đồng thời.
- Local type name chỉ trong block, nên công bố static API của type ra ngoài cũng không thuận tiện.

Nếu chỉ muốn accumulator tạm trong một method call, sử dụng **local variable** hoặc object instance tùy nhu cầu, không đưa thành static field của local class.

### Static constant hợp lý hơn?

`static final int LIMIT = 10` trong local class có thể hợp lệ và giúp nhóm constant với helper code. Nhưng nếu constant là dùng chung trong nhiều methods, một private static final field của enclosing class có thể làm ý định rõ hơn.

## 36. Static state tồn tại qua các lần gọi method

Lưu **`LocalStaticLifetimeDemo.java`**:

```java
public class LocalStaticLifetimeDemo {
    static int next() {
        class Local {
            static int counter = 0;

            static int increment() {
                return ++counter;
            }
        }

        return Local.increment();
    }

    public static void main(String[] args) {
        System.out.println(next());
        System.out.println(next());
        System.out.println(next());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 LocalStaticLifetimeDemo.java
java LocalStaticLifetimeDemo
```

**Stdout:**

```text
1
2
3
```

Một khai báo local class trong source được biên dịch thành một type có static state; việc method `next()` trả về **không reset static field**. `counter` không phải một `int counter = 0` local variable của từng lần gọi.

### Đừng dùng thí dụ này cho concurrent counter

`++counter` không phải atomic increment giữa nhiều threads. Ví dụ chỉ chạy tuần tự. Nếu ứng dụng thật cần counter an toàn, dùng synchronization hoặc `AtomicInteger` với scope/lifecycle thích hợp.

## 37. Tránh nhầm local normal class với anonymous class và lambda

Một anonymous class:

```java
Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println("done");
    }
};
```

không có tên khai báo class như `Local`, nên không có vị trí để ghi modifier kiểu `public class Local`.

Lambda:

```java
Runnable task = () -> System.out.println("done");
```

không phải local class declaration. Nó có rules riêng về functional interfaces, lexical `this` và capture.

**Nếu đề bài hỏi modifier của “lớp cục bộ thông thường”**, trước hết phải xác định có dòng `class Local { ... }` nằm trong block hay không. Đừng dùng rules của lambda hoặc anonymous class để trả lời thay cho local normal class.

## 38. Phân loại lỗi theo nơi modifier xuất hiện

Cho các tình huống:

**A. Lỗi tại local class declaration**

```java
void f() {
    private class Local {
    }
}
```

Lỗi vì `private` không được phép trên local declaration.

**B. Lỗi tại local class declaration**

```java
void f() {
    static class Local {
    }
}
```

Lỗi vì `static` trên chính local normal class declaration.

**C. Hợp lệ trên Java 17**

```java
void f() {
    class Local {
        private static int value = 7;

        static int read() {
            return value;
        }
    }

    System.out.println(Local.read());
}
```

`private` là modifier của field, `static` là modifier của field/method; local class declaration không có modifier bị cấm.

**D. Lỗi static context**

```java
void f() {
    int captured = 7;

    class Local {
        static int read() {
            // return captured; // Không hợp lệ.
            return 0;
        }
    }
}
```

Lỗi ở việc static method truy cập captured local variable; không phải vì local class cấm static method.

Các mã A/B là **compile-negative snippets**, không đưa nguyên chúng vào cùng source file dùng để chạy ví dụ C/D.

## 39. Bảng chẩn đoán theo thông báo compiler

| Vấn đề | Nguyên nhân thật | Cách sửa |
| --- | --- | --- |
| `modifier private not allowed here` khi viết `private class Local` | Local type không phải member | Bỏ modifier hoặc đổi thành member class theo nhu cầu |
| `modifier static not allowed here` khi viết `static class Local` | `static` bị cấm trên local type declaration | Bỏ `static` ở dòng class |
| Không compile `sealed class Local` | Local declarations cấm sealed | Chuyển sealed hierarchy ra member/top-level scope |
| Không compile `abstract final class Local` | Modifiers mâu thuẫn | Chọn abstract hoặc final |
| Không thể `new AbstractLocal()` | Class abstract | Tạo concrete subclass |
| Static method không đọc `offset` | Static context không capture enclosing local variable | Truyền parameter hoặc dùng instance method |
| Static method không đọc `Outer.this` | Không có enclosing instance trong static member context | Truyền Outer reference |
| `threshold` captured nhưng bị gán lại | Không effectively final | Giữ biến không gán lại hoặc đổi data flow |
| Local record đọc biến local enclosing | Record implicitly static | Truyền qua component/parameter |
| Local interface cố ghi `static interface` | `static` ở local declaration bị cấm | Bỏ keyword, implicitly static |
| Tưởng static field reset mỗi method call | Static state thuộc local type | Dùng local/instance state nếu cần từng invocation |
| Compiler cũ cấm static method trong local class | Source release trước Java 16 | Xác định target release hoặc dùng compatible alternative |
| `class Local` không nhìn thấy từ method khác | Lexical scope của local type | Return interface hoặc tách member/top-level class |
| Nội bộ Local có public method nhưng caller không dùng được tên Local | Visibility của type khác method member | Công bố interface/supertype phù hợp |

## 40. Bài tập 1 — Trắc nghiệm modifier cơ bản

Trong Java 17, lựa chọn nào được phép **trước `class Local` khai báo trong method block**?

A. `public`  
B. `private`  
C. `final`  
D. `static`

**Đáp án: C.** `final` hợp lệ. `public`, `private`, `static` bị cấm trên local normal class declaration. Nếu có `abstract`, nó cũng có thể hợp lệ riêng rẽ.

## 41. Bài tập 2 — `protected` có hợp lệ không?

```java
void run() {
    protected class Local {
    }
}
```

**Đáp án:** Không biên dịch. `protected` là access modifier thích hợp cho member class, không cho local class.

## 42. Bài tập 3 — Static method của local class Java 17

```java
void run() {
    class Local {
        static int twice(int x) {
            return x * 2;
        }
    }

    System.out.println(Local.twice(4));
}
```

**Đáp án:** Hợp lệ trong Java 17; in `8`. `static` đang gắn với **method** chứ không nằm trước `class Local`.

## 43. Bài tập 4 — Static method của local class Java 8

Cùng đoạn bài 3 được biên dịch với source level Java 8.

**Đáp án:** Quy tắc của Java 8 không cho local inner class khai báo một static method như vậy. Không dùng kết luận Java 8 cho `--release 17`.

## 44. Bài tập 5 — Phân biệt vị trí `static`

```java
class Outer {
    static class Member {
    }

    void method() {
        class Local {
        }
    }
}
```

**Đáp án:** `static` hợp lệ vì `Member` là member nested class. `Local` được khai báo trong block, không phải member class, nên không được thêm `static` trước `class Local`.

## 45. Bài tập 6 — Local final và class mutable

Một `final class Local` có field `int count` và method tăng count.

**Đáp án:** Class vẫn mutable. `final` trên class chỉ cấm subclass, không cấm update instance fields.

## 46. Bài tập 7 — Local abstract

```java
void run() {
    abstract class Local {
        abstract void execute();
    }
}
```

**Đáp án:** Khai báo hợp lệ. Nhưng `new Local()` không hợp lệ vì abstract; cần concrete subclass implement method.

## 47. Bài tập 8 — `abstract final`

```java
void run() {
    abstract final class Local {
    }
}
```

**Đáp án:** Không biên dịch do hai class modifiers mâu thuẫn. Không phải do class local; kết hợp này cũng bất hợp lệ với class thông thường khác.

## 48. Bài tập 9 — Private field trong local class

```java
void run() {
    class Local {
        private int count;
    }
}
```

**Đáp án:** Hợp lệ. `private` là modifier của **field count**, không của declaration `class Local`.

## 49. Bài tập 10 — Public method trong local class

```java
void run() {
    class Local {
        public int answer() {
            return 42;
        }
    }
}
```

**Đáp án:** Hợp lệ. `public` thuộc method `answer`, không làm type Local thành public member/top-level type.

## 50. Bài tập 11 — Static initializer Java 17

```java
void run() {
    class Local {
        static int value;
        static {
            value = 7;
        }
    }
}
```

**Đáp án:** Hợp lệ trên Java 17. Static initializer/field là **members/declarations bên trong** local inner class, không phải `static` trên local class declaration.

## 51. Bài tập 12 — Local static nested member type

```java
void run() {
    class Local {
        static class Detail {
        }
    }
}
```

**Đáp án:** Hợp lệ trong Java 17. `Detail` là static nested member type bên trong Local; Local vẫn là local normal class không static ở declaration.

## 52. Bài tập 13 — Static method capture local variable?

```java
void run() {
    int factor = 2;

    class Local {
        static int compute() {
            // return factor * 10;
            return 0;
        }
    }
}
```

**Đáp án:** Nếu bỏ comment để trả `factor * 10`, sẽ bị compiler từ chối. Static method không capture local variable của enclosing method qua ranh giới static context. Truyền factor làm parameter.

## 53. Bài tập 14 — Instance method capture local variable?

```java
void run() {
    int factor = 2;

    class Local {
        int compute() {
            return factor * 10;
        }
    }

    System.out.println(new Local().compute());
}
```

**Đáp án:** Hợp lệ và in `20`, vì factor effectively final và được sử dụng trong instance method thích hợp.

## 54. Bài tập 15 — Captured variable bị gán lại

```java
void run() {
    int factor = 2;

    class Local {
        int compute() {
            return factor;
        }
    }

    factor = 3;
}
```

**Đáp án:** Không compile vì factor không effectively final. Bỏ lần gán lại hoặc đổi thiết kế; không phải lỗi do local class thiếu `public`.

## 55. Bài tập 16 — Local record

```java
void run() {
    record Point(int x, int y) {
    }
}
```

**Đáp án:** Hợp lệ trong Java 17. Local record implicitly static và không phải local normal inner class.

## 56. Bài tập 17 — Ghi `static record`?

```java
void run() {
    static record Point(int x, int y) {
    }
}
```

**Đáp án:** Không hợp lệ. Modifier `static` ở local declaration bị cấm, dù bản thân local record implicitly static.

## 57. Bài tập 18 — Local enum

```java
void run() {
    enum Status {
        NEW, DONE
    }
}
```

**Đáp án:** Hợp lệ. Local enum implicitly static, không cần hoặc được ghi `static` trước `enum`.

## 58. Bài tập 19 — Local interface

```java
void run() {
    interface Rule {
        boolean allows(int n);
    }
}
```

**Đáp án:** Hợp lệ trong Java 17. Local normal interface implicitly static, không capture outer local variables theo cách local normal inner class.

## 59. Bài tập 20 — Local sealed hierarchy

```java
void run() {
    sealed class Parent permits Child {
    }

    final class Child extends Parent {
    }
}
```

**Đáp án:** Không hợp lệ; JLS `14.3 cấm `sealed` trên local class declaration. Muốn sealed hierarchy, tổ chức thành member hoặc top-level hierarchy thích hợp.

## 60. Bài tập 21 — Thêm `private` để giấu Local?

Một developer muốn local type chỉ visible trong method nên viết `private class Local`.

**Đáp án:** Không cần và không hợp lệ. Local type name đã bị giới hạn lexical scope; xóa `private`. Nếu muốn class giấu ở cấp enclosing class nhưng dùng được từ nhiều methods, chọn `private static class MemberHelper` phù hợp.

## 61. Bài tập 22 — Static local state reset mỗi lần gọi?

Một method khai báo local class với `static int n = 0`, static method tăng n. Gọi method ba lần trong cùng class loader.

**Đáp án:** Không tự reset `n` về 0 sau mỗi invocation. Static state thuộc local class type, không thuộc mỗi method stack frame.

## 62. Bài tập 23 — Reflection và static members

Một local class có `static void run()`. `clazz.isLocalClass()` có thành false không?

**Đáp án:** Không. Nó vẫn là local class do declaration location; `isLocalClass()` có thể là true và `Modifier.isStatic(clazz.getModifiers())` không bắt buộc true vì static method không phải class-level static modifier.

## 63. Bài tập 24 — Annotation

```java
void run() {
    @Deprecated
    class Local {
    }
}
```

**Đáp án:** Có thể hợp lệ, vì annotation áp lên khai báo type thích hợp. Annotation không giống access modifier `private/public/protected`.

## 64. Bài tập 25 — Enclosing instance

Một local normal class ở instance method dùng `Outer.this.name`; sau đó chuyển nguyên block sang static method.

**Đáp án:** Không thể dùng `Outer.this` trong static method context vì không có enclosing Outer instance. Cần explicit Outer reference hoặc giữ instance context.

## 65. Bài tập 26 — Chọn thiết kế khác nếu cần public API

Một local class `Validator` cần được các packages khác gọi trực tiếp bằng tên.

**Đáp án:** Local class không cung cấp tên type ra ngoài lexical block. Nên chuyển logic thành public/package-private top-level class, member nested type accessible, hoặc công bố interface/factory phù hợp; không thể giải quyết bằng `public class Validator` bên trong method.

## 66. Bài tập 27 — Phân biệt compile error và runtime behavior

Cho local class với static initializer và counter đúng Java 17. Một người nói “chắc chắn lỗi vì local class không được static”.

**Đáp án:** Cần chỉ đúng **vị trí `static`**. Trước `class Local` thì lỗi; trong body trên static field/method/initializer thì Java 17 cho phép. Chỉ sau khi code compile mới bàn tới lifetime/static initialization behavior.

## 67. Bài tập 28 — Static variable của enclosing method?

```java
void run() {
    static int count = 0;
}
```

**Đáp án:** Không hợp lệ. Java không hỗ trợ static local variable declaration như C. Đây là quy tắc của **local variable**, khác với `static int count` đặt **bên trong local class** ở Java 17.

## 68. Bài tập 29 — Có nên tạo static counter bằng local class?

Một service cần global counter thread-safe. Developer đặt mutable static field trong local class vì chỉ một method sử dụng.

**Đáp án:** Ngữ pháp có thể hợp lệ Java 17, nhưng design nên xét concurrency, discoverability, initialization và ownership. Một dedicated class/field có tên thích hợp với `AtomicInteger` hay synchronization đúng thường rõ hơn.

## 69. Bài tập 30 — Modifier áp cho ba cấp khác nhau

Xét ba đoạn:
- `private static class Helper` đặt trực tiếp trong class body.
- `class Local { static int x; }` đặt trong method body.
- `static class Local {}` đặt trong method body.

**Đáp án:** Đoạn một hợp lệ cho member nested; đoạn hai hợp lệ Java 17 vì static modifier thuộc **field**; đoạn ba sai vì static modifier gắn với **local class declaration**.

## 70. Checklist ôn tập và review source code

1. Khai báo `class Local` nằm **trong block**, hay trực tiếp trong class body?
2. Nếu ở trong block, đó có phải **local normal class** không?
3. `public/protected/private` có đang đặt **trước `class Local`** không? Nếu có: lỗi.
4. `static` có đang đặt **trước `class Local`** không? Nếu có: lỗi.
5. `sealed/non-sealed` có đang đặt trên local declaration không? Nếu có: lỗi.
6. `final` có đặt ở khai báo Local không? Hợp lệ nhưng cấm extends.
7. `abstract` có đặt ở khai báo Local không? Hợp lệ nhưng không trực tiếp new.
8. Có dùng `abstract final` chung không? Nếu có: lỗi.
9. Có annotation trước declaration không? Đã kiểm tra `@Target` chưa?
10. Có dùng `strictfp` và hiểu Java 17 luôn strict floating-point không?
11. Có phân biệt **modifier của class declaration** với **modifier của field/method** không?
12. Nếu có static field trong Local, project target có phải **Java 16+** không?
13. Nếu có static method trong Local, code đó có cần capture biến enclosing method không?
14. Nếu có static initializer trong Local, class initialization/lifetime đã rõ chưa?
15. Nếu có static nested member type bên trong Local, đã phân biệt với `static class Local` chưa?
16. Có static mutable state cần synchronization khi concurrency không?
17. Có hiểu static field không reset theo mỗi method invocation không?
18. Local class nằm trong static method hay instance method?
19. Nếu trong static method, có vô tình truy cập `Outer.this`/instance field trần không?
20. Instance method của local class có capture biến final/effectively final đúng không?
21. Captured local variable có definitely assigned và trong scope hợp lệ không?
22. Có gán lại captured variable về sau khiến nó mất effectively final không?
23. Có nhầm final reference với immutable referent không?
24. Có phân biệt local normal class với local record/enum/interface không?
25. Nếu local record/enum/interface, có nhớ **implicitly static** nhưng cấm explicit modifier `static` không?
26. Local record có đang cố capture outer local variables không?
27. Có dùng local sealed class/interface trái `14.3` không?
28. Tên local class có bị dùng ngoài lexical scope không?
29. Nếu cần reusable type công khai, có nên tách member/top-level class không?
30. Có đang dựa vào compiler-generated `$1` class name để lập luận không?
31. Có tách các snippets **compile-negative** khỏi runnable files không?
32. Mỗi ví dụ runnable có đúng tên public class/file và lệnh `javac --release 17` không?
33. Có phân biệt compile-time modifier error với runtime class initialization không?
34. Khi nâng source release, có rà soát hướng dẫn Java 8 cũ về static inner members không?
35. Đã tra đúng JLS SE 17 `14.3 và `8.1.3 khi cần lý giải chính xác chưa?

## 71. Ghi nhớ trọng tâm

- **Local normal class** được khai báo trong block, có tên cục bộ và **không phải member class**.
- Trên **khai báo** local normal class, Java 17 **cấm `public`, `protected`, `private`, `static`, `sealed`, `non-sealed`**.
- `final` và `abstract` hợp lệ **riêng rẽ**; không được kết hợp cả hai trên cùng một class.
- `strictfp` vẫn nằm trong syntax của JLS 17 nhưng không đem lại thay đổi hữu ích đối với always-strict floating-point.
- Class-level modifier `static` bị cấm không đồng nghĩa body của Local cấm **static members**.
- **Từ Java 16**, inner classes, bao gồm local normal classes, có thể khai báo static fields/methods/initializers/nested types; Java 17 giữ quy tắc này.
- Static method trong local class vẫn là **static context**: không có `this` và không capture enclosing local variables.
- Local class trong static method là hợp lệ, nhưng không vì thế được viết `static class Local`.
- Local interface/record/enum có thể xuất hiện trong block Java 17; chúng **implicitly static** nhưng không được ghi rõ `static` ở local declaration.
- Tên Local chỉ sống trong lexical scope; instance có thể sống lâu hơn method qua một interface/supertype.
- Hãy đọc **đúng vị trí keyword** và **đúng Java source release**, thay vì kết luận bằng khẩu quyết “local class không được static”.

## Tài liệu chuẩn để đối chiếu

- **Java Language Specification, Java SE 17, `14.3 — Local Class and Interface Declarations:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.3
- **JLS Java SE 17, `8.1.1 — Class Modifiers:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.1
- **JLS Java SE 17, `8.1.3 — Inner Classes and Enclosing Instances:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.3

**Kết luận:** Đối với local normal class trong Java 17, hạn chế quan trọng nằm ở **modifier của dòng khai báo class** và **ngữ cảnh truy cập**, chứ không phải cấm tất cả static declarations trong thân class. Phân biệt được hai tầng ấy là chìa khóa để viết code đúng và hiểu vì sao ví dụ từ Java 8 có thể cho kết luận khác Java 17.
