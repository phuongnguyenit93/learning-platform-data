# Phạm vi tên, thời gian tồn tại và hiện tượng che khuất tên trong trường dữ liệu Java

Khi một class Java có nhiều trường (field), tham số và biến cục bộ, cùng một tên như `count` có thể xuất hiện ở nhiều nơi. Đoạn mã `count = count + 1` sẽ tác động đến biến nào? Tại sao `this.count` và `super.count` có thể cho hai giá trị khác nhau? Sau khi phương thức kết thúc, trường của object có mất đi không? Đó là những vấn đề thuộc **phạm vi tên (scope)**, **thời gian tồn tại (lifetime)** và **che khuất tên (shadowing/hiding)**.

Bài này tập trung vào **trường dữ liệu của class**, đồng thời dùng biến cục bộ, tham số và kế thừa để làm rõ cơ chế phân giải tên. Các ví dụ chạy được trên Java 17 trở lên, trừ những đoạn có ghi rõ *ví dụ lỗi biên dịch*.

Mục tiêu:

1. Xác định từ vị trí mã nguồn nào có thể dùng tên của một trường.
2. Phân biệt *tên có trong phạm vi* với *đối tượng/giá trị còn tồn tại khi chạy*.
3. Nhận diện một trường instance và một trường `static` tồn tại theo những điều kiện khác nhau.
4. Dự đoán chính xác khi tham số hoặc biến cục bộ che khuất trường; dùng `this.field` khi cần.
5. Phân biệt **field hiding** trong kế thừa với **method overriding**; biết tác dụng của `super.field`.
6. Hiểu giới hạn của việc dự đoán thu gom rác (GC), tránh suy luận rằng một biến ra khỏi block sẽ lập tức giải phóng object.

## 1. Ba khái niệm dễ bị nhầm là một

| Khái niệm | Câu hỏi thực sự | Được quyết định chủ yếu bởi |
| --- | --- | --- |
| **Scope / phạm vi tên** | Ở vị trí nào trong mã nguồn, một tên đơn giản như `balance` có thể được tham chiếu? | Cấu trúc khai báo, block, class, package và quy tắc phân giải tên của ngôn ngữ |
| **Accessibility / quyền truy cập** | Mã ở vị trí đó có được phép truy cập thành viên không? | `private`, `protected`, package-private, `public`, quy tắc kế thừa/module |
| **Lifetime / thời gian tồn tại** | Khi thực thi, biến, trường hoặc object còn có ý nghĩa/tồn tại tới lúc nào? | Lần gọi phương thức, vòng đời instance, việc khởi tạo class, khả năng còn được tham chiếu |
| **Shadowing/hiding / che khuất tên** | Nếu có nhiều khai báo dùng cùng tên, tên không đủ điều kiện sẽ biểu thị khai báo nào? | Quy tắc phân giải tên, thứ tự khai báo, quan hệ class và inheritance |

**Ví dụ quan trọng:** Một trường `private int count` vẫn **tồn tại trong object** sau khi một phương thức vừa gọi kết thúc, dù biến cục bộ `count` của phương thức ấy không còn được dùng trong lần gọi đó. Một trường `static` có thể còn tồn tại sau khi mọi instance của class đã không còn được dùng. Ngược lại, một tên có thể nằm trong phạm vi từ góc nhìn mã nguồn nhưng bị che khuất bởi một khai báo gần hơn.

Phạm vi tên là đặc tính **tĩnh** của mã nguồn; thời gian tồn tại là câu chuyện **khi chạy**. Quyền truy cập là một điều kiện riêng: việc nhìn thấy một tên trong cấu trúc class không tự cấp quyền đọc mọi field `private` của class khác.

## 2. Phạm vi của trường instance và trường static

Một **field** là biến được khai báo trực tiếp trong thân class hoặc interface theo quy tắc Java, khác với biến được khai báo trong thân method/constructor/block.

~~~java
class CourseProgress {
    private String courseName;  // instance field
    private int lessonsDone;     // instance field
    private static int instances; // static field

    CourseProgress(String courseName) {
        this.courseName = courseName;
        instances++;
    }

    void completeLesson() {
        lessonsDone++;
    }
}
~~~

Đây là **đoạn class minh họa**; ví dụ chạy hoàn chỉnh nằm ở phần sau.

- `courseName` và `lessonsDone` thuộc về **mỗi instance** của `CourseProgress`. Hai object có thể có giá trị khác nhau.
- `instances` là field `static`, thuộc class tương ứng trong ngữ cảnh class loader; mọi instance thông thường cùng dùng một field `instances` của class đó.
- Phạm vi tên đơn giản của một field được khai báo trong class bao gồm phần thân class theo quy tắc ngôn ngữ, với những ngoại lệ về **forward reference trong initializer** và về tên bị che khuất.
- Một instance method có thể tham chiếu instance field bằng tên không đủ điều kiện (`lessonsDone`) hoặc bằng `this.lessonsDone`.
- Từ static method không có `this`; để đọc instance field cần có một tham chiếu đến instance, như `progress.lessonsDone`, và phải thỏa điều kiện truy cập.
- Trường `private` của `CourseProgress` không được đọc trực tiếp từ một class độc lập bên ngoài phạm vi truy cập hợp lệ. Phương thức public/package-private có thể cung cấp hành vi hoặc dữ liệu cần thiết.

### Phạm vi từ khi khai báo và thứ tự lệnh thực thi

Trong class, các thành viên có thể được khai báo trước hoặc sau phương thức sử dụng chúng:

~~~java
class DeferredField {
    int read() {
        return number;
    }

    private int number = 7;
}
~~~

Đoạn class hợp lệ: tên `number` trong `read()` được phân giải tới field mặc dù khai báo field nằm phía dưới phương thức. Quy tắc này **không** có nghĩa mọi cách dùng field trước dòng khai báo đều hợp lệ: các initializer có hạn chế forward reference, sẽ được phân tích ở mục 9.

### Trường là thành viên, không phải biến cục bộ

Trong ví dụ:

~~~java
class Sample {
    int field = 1;

    void work(int parameter) {
        int local = 2;
        if (parameter > 0) {
            int insideBlock = 3;
            field += local + insideBlock;
        }
        // insideBlock không còn trong phạm vi tên ở đây
    }
}
~~~

`field` là thành viên lưu trạng thái instance. `parameter` chỉ hiện diện trong lần gọi `work`. `local` là biến cục bộ ở block method; `insideBlock` chỉ được khai báo trong block `if`. Mã sau block không thể dùng tên `insideBlock` vì **đã hết scope**, không phải vì một field của object vừa tự biến mất.

## 3. Thời gian tồn tại của instance field

Khi thực thi `new CourseProgress("Java")`, Java tạo một instance và cấp những instance field mà object cần. Trong quá trình khởi tạo, các field nhận **giá trị mặc định** trước khi những field initializer và constructor liên quan chạy theo thứ tự khởi tạo được quy định.

| Kiểu field | Giá trị mặc định trước khởi tạo tường minh |
| --- | --- |
| `byte`, `short`, `int`, `long` | `0` theo kiểu tương ứng |
| `float`, `double` | `0.0` theo kiểu tương ứng |
| `char` | ký tự null `'\\u0000'` |
| `boolean` | `false` |
| Kiểu tham chiếu như `String`, `CourseProgress`, mảng | `null` |

Những giá trị mặc định không thay thế trách nhiệm khởi tạo dữ liệu hợp lệ; chẳng hạn `null` có thể không phải trạng thái cho phép đối với một tên khóa học.

**Instance field tồn tại cùng instance về mặt ngữ nghĩa**, không bị xóa chỉ vì method sử dụng nó kết thúc. Các lần gọi method sau có thể đọc đúng trạng thái đã cập nhật của object nếu vẫn dùng cùng instance.

~~~text
Tạo object bằng new
       |
       v
Các field instance được thiết lập
       |
       v
Gọi method A -> thay đổi field
       |
       v
Method A trả về
       |
       v
Gọi method B -> vẫn đọc được giá trị field mới
       |
       v
Object không còn cần thiết/không còn reachable theo quy tắc JVM
       |
       v
Bộ thu gom rác có thể thu hồi bộ nhớ trong tương lai
~~~

**Không dự đoán thời điểm GC:** Java không bảo đảm object được thu hồi ngay khi một biến ra khỏi scope, ngay lúc method trả về hoặc ngay sau khi gán một tham chiếu thành `null`. JVM có thể tối ưu hóa và xác định object không còn cần thiết sớm hơn cách ta suy luận từ tên biến; đồng thời object có thể còn được tham chiếu qua nhiều đường khác nhau. Hãy viết chương trình dựa trên hành vi và tính đúng đắn, không dựa vào thời điểm GC.

### Biến tham chiếu và object có vòng đời khác nhau

~~~java
CourseProgress first = new CourseProgress("Java");
CourseProgress alias = first;
~~~

`first` và `alias` là **hai biến tham chiếu**, nhưng chúng trỏ tới **cùng một object**. Khi phạm vi của `first` kết thúc, object không đương nhiên biến mất nếu `alias` hay một đường tham chiếu khác vẫn giữ nó.

~~~text
first ------\
             > CourseProgress object { courseName: "Java", ... }
alias ------/
~~~

Mũi tên là mô hình quan hệ tham chiếu; không phải sơ đồ địa chỉ bộ nhớ thực tế. Khả năng sống của object được đánh giá dựa trên tính reachable/nhu cầu thực thi, không dựa vào một tên biến duy nhất.

### `final` không tự biến object thành bất biến

`final CourseProgress progress = new CourseProgress("Java");` khiến biến `progress` không thể được gán tham chiếu khác sau khởi tạo theo quy tắc Java. Tuy nhiên nếu `completeLesson()` được phép sửa `lessonsDone`, lời gọi `progress.completeLesson()` vẫn hợp lệ. `final` trên biến tham chiếu không rút ngắn hay kéo dài lifetime của object theo một quy tắc đơn giản, và không tự đóng băng những field mutable của object được tham chiếu.

## 4. Thời gian tồn tại của static field

Trường `static` gắn với class khi class được chuẩn bị/khởi tạo và được duy trì theo trạng thái runtime của class ấy, thay vì gắn với từng instance. Chẳng hạn hai object `CourseProgress` dùng chung một `instances` trong cùng ngữ cảnh class.

Phân biệt:

| | Instance field | Static field |
| --- | --- | --- |
| Thuộc về | Từng object | Class được JVM định nghĩa/nạp trong ngữ cảnh tương ứng |
| Số bản dữ liệu | Mỗi instance một giá trị field | Một field cấp class cho mỗi class runtime tương ứng |
| Truy cập thích hợp | `object.field`, `this.field` bên trong instance | `ClassName.field` |
| Khi không còn instance | Trường của instance mất cùng object khi object bị thu hồi | Static field vẫn có thể tồn tại khi class còn được runtime giữ |
| Tác động thay đổi | Thường chỉ vào instance đó | Mọi mã truy cập cùng class runtime có thể thấy cùng static field |

Ví dụ gọi `CourseProgress.instances` từ code **bên ngoài** class ở đoạn trước là không hợp lệ vì field đó `private`. Muốn đọc hãy cung cấp `static` method phù hợp, như `totalCreated()`, hoặc thử trực tiếp bên trong class. **Access modifier vẫn có hiệu lực** dù trường là static.

Một static field không nhất thiết sống đến khi cả JVM tắt trong mọi ứng dụng: class có thể được unload khi điều kiện thu gom class loader và các yếu tố runtime phù hợp; các hệ thống plugin hoặc server nạp class nhiều lần là ví dụ cần quan tâm. Đối với ứng dụng console nhỏ dùng application class loader, có thể xem static state là tồn tại trong thời gian class còn được dùng cho quá trình chạy, nhưng đó là mô hình đơn giản để học chứ không phải bảo đảm “static sống vĩnh viễn”.

Nếu một static field chứa tham chiếu tới object, tham chiếu này có thể góp phần giữ object reachable. Ví dụ lưu danh sách object trong một static collection lâu dài có thể khiến bộ nhớ không được giải phóng như mong muốn. Hãy chủ động quản lý các tham chiếu lâu dài khi ứng dụng cần vòng đời tài nguyên cụ thể.

**Chú ý:** static field không an toàn cho nhiều luồng chỉ vì nó là static. Các thao tác như `counter++` có thể bị race condition nếu nhiều luồng cùng cập nhật mà không có cơ chế đồng bộ thích hợp.

## 5. So sánh scope và lifetime qua một chương trình Java 17+ hoàn chỉnh

Lưu tệp **`ScopeLifetimeDemo.java`** bằng UTF-8:

~~~java
public class ScopeLifetimeDemo {
    static final class Meter {
        private static int createdCount = 0;

        private final String name;
        private int reading = 0;

        Meter(String name) {
            this.name = name;
            createdCount++;
        }

        void add(int amount) {
            int oldReading = reading;
            reading = oldReading + amount;

            if (amount > 0) {
                String event = "increased";
                System.out.println(name + " " + event + " by " + amount);
            }
            // event không có trong scope tên tại đây.
        }

        int reading() {
            return reading;
        }

        static int createdCount() {
            return createdCount;
        }
    }

    public static void main(String[] args) {
        Meter first = new Meter("A");
        Meter second = new Meter("B");

        first.add(3);
        first.add(2);
        second.add(7);

        System.out.println("A: " + first.reading());
        System.out.println("B: " + second.reading());
        System.out.println("Created: " + Meter.createdCount());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 ScopeLifetimeDemo.java
java ScopeLifetimeDemo
~~~

Stdout:

~~~text
A increased by 3
A increased by 2
B increased by 7
A: 5
B: 7
Created: 2
~~~

Giải thích theo từng loại dữ liệu:

1. `first` và `second` là biến cục bộ trong `main`; chúng giữ hai tham chiếu đến hai object `Meter` khác nhau.
2. `name` và `reading` là instance field. Mỗi Meter có dữ liệu riêng; sau ba lần gọi `add`, Meter A có `reading = 5`, Meter B có `reading = 7`.
3. `oldReading` là biến cục bộ mới trong mỗi lần gọi `add`. Lần gọi trước kết thúc không làm field `reading` mất giá trị.
4. `event` chỉ có thể được dùng bên trong block `if`; mã ngoài block không được phép gọi tên này.
5. `createdCount` là một static field của `Meter`, tăng một lần trong mỗi lần chạy constructor và có giá trị 2 sau khi tạo hai object.
6. `name` là field `final`, không được gán lại sau khởi tạo bình thường, còn `reading` là field mutable. Sự khác biệt này độc lập với việc field là instance hay static.

Nếu thêm lệnh `System.out.println(event);` bên ngoài block `if`, chương trình **không biên dịch** vì không tìm được tên `event` trong scope. Ngược lại, câu lệnh `System.out.println(reading);` bên trong instance method `add` hợp lệ vì field `reading` vẫn trong phạm vi tên của class.

## 6. Shadowing: tham số hoặc biến cục bộ che khuất field

**Shadowing** xảy ra khi một khai báo ở phạm vi gần hơn làm cho tên đơn giản vốn có thể biểu thị khai báo khác nay biểu thị khai báo mới. Một trường hợp rất thường gặp là tham số constructor trùng tên instance field.

~~~java
class Account {
    private String owner;

    Account(String owner) {
        this.owner = owner;
    }
}
~~~

Trong constructor, hai chữ `owner` không trỏ đến cùng một biến:

- `owner` **không có tiền tố** ở bên phải phép gán là **tham số** `owner`.
- `this.owner` ở bên trái là **field** `owner` của object hiện tại.
- Nếu viết `owner = owner;`, cả hai tên đều là tham số; câu lệnh tự gán tham số, field không được cập nhật và có thể giữ `null`.

`this` là tham chiếu đến instance hiện tại trong ngữ cảnh instance phù hợp. Trong static method, không có `this` nên không thể giải quyết field bằng `this.field`.

### Ví dụ đầy đủ: tên `value` ở ba vị trí

Tạo tệp **`FieldShadowingDemo.java`**:

~~~java
public class FieldShadowingDemo {
    static final class Counter {
        private int value = 10;

        Counter(int value) {
            this.value = value;
        }

        void add(int value) {
            int before = this.value;
            this.value = before + value;
            System.out.println("Parameter: " + value);
            System.out.println("Field: " + this.value);
        }

        void printNames() {
            int value = 99;
            System.out.println("Local: " + value);
            System.out.println("Field: " + this.value);

            if (value > 0) {
                String message = "positive";
                System.out.println("Block: " + message);
            }
        }

        int current() {
            return value;
        }
    }

    public static void main(String[] args) {
        Counter counter = new Counter(5);
        counter.add(3);
        counter.printNames();
        System.out.println("Result: " + counter.current());
    }
}
~~~

~~~bash
javac -encoding UTF-8 FieldShadowingDemo.java
java FieldShadowingDemo
~~~

Stdout:

~~~text
Parameter: 3
Field: 8
Local: 99
Field: 8
Block: positive
Result: 8
~~~

Từng điểm cần nhận biết:

1. Trong constructor, tham số `value` che khuất field cùng tên. `this.value = value` gán giá trị 5 vào field.
2. Trong `add(int value)`, `value` không có tiền tố là tham số 3; `this.value` là field đang mang giá trị 5 rồi được cập nhật lên 8.
3. Trong `printNames()`, biến cục bộ `int value = 99` che khuất field, nên `value` cho 99 còn `this.value` cho 8.
4. `message` chỉ có phạm vi tên trong block `if`.
5. Trong `current()` không có tham số hay biến cục bộ nào tên `value`, nên `return value;` trực tiếp đọc field.

**Phạm vi che khuất không xóa field.** Field vẫn nằm trong object, vẫn có thể được truy cập bằng `this.value` và vẫn giữ giá trị sau khi `printNames()` kết thúc.

### Không phải mọi khai báo trùng tên đều được phép

Trong Java, không được khai báo hai biến cục bộ/trùng tham số cùng tên ở **những phạm vi lồng nhau đang chồng lấp** trong cùng method. Ví dụ sau **cố ý không biên dịch**:

~~~java
void invalid(int count) {
    if (count > 0) {
        int count = 2; // Lỗi: tên biến trùng tham số trong scope chồng lấp.
    }
}
~~~

Một tình huống khác cũng không hợp lệ:

~~~java
void invalidAgain() {
    int count = 1;
    {
        int count = 2; // Lỗi: không thể khai báo lại local trong block lồng nhau.
    }
}
~~~

Hai đoạn là **minh họa lỗi**, không được ghép vào các ví dụ chạy độc lập ở trên. Ngược lại, local/parameter **được phép che khuất field** của class, vì hai loại khai báo có quy tắc tên khác nhau. Đừng suy luận rằng Java cho phép biến cục bộ lồng nhau shadow mọi biến cục bộ như một số ngôn ngữ khác.

### Biến cục bộ cùng tên ở hai block rời nhau

~~~java
void separateBlocks(boolean flag) {
    if (flag) {
        int score = 1;
        System.out.println(score);
    } else {
        int score = 2;
        System.out.println(score);
    }
}
~~~

Đây là **đoạn method minh họa**, có thể đặt trong một class. Hai `score` nằm ở hai block không chồng lấp nên hợp lệ. Nếu có field cũng mang tên `score`, tên đơn giản bên trong từng block sẽ biểu thị biến cục bộ đang có hiệu lực.

## 7. Shadowing khác field hiding trong kế thừa

Khi một subclass khai báo field có cùng tên field kế thừa từ superclass, field của subclass **che khuất** field của superclass ở những nơi thích hợp. Đây thường được gọi là **field hiding**. Hai field vẫn là hai thành viên riêng; subclass không ghi đè một field theo cơ chế đa hình của method.

**Cần tách hai quy tắc:**

- Truy cập field như `reference.label` được phân giải theo **kiểu khai báo (compile-time type)** của biểu thức tham chiếu và quy tắc truy cập/hiding.
- Gọi instance method được override như `reference.describe()` thường được chọn theo **kiểu runtime** của đối tượng (dynamic dispatch), sau khi compiler xác định chữ ký phương thức có thể gọi.

Tạo **`FieldHidingDemo.java`**:

~~~java
public class FieldHidingDemo {
    static class Parent {
        String label = "parent";

        String describe() {
            return "Parent.describe";
        }
    }

    static class Child extends Parent {
        String label = "child";

        @Override
        String describe() {
            return "Child.describe";
        }

        void printBothFields() {
            System.out.println("this.label: " + this.label);
            System.out.println("super.label: " + super.label);
        }
    }

    public static void main(String[] args) {
        Child child = new Child();
        Parent parentView = child;

        System.out.println("child.label: " + child.label);
        System.out.println("parentView.label: " + parentView.label);
        System.out.println("child.describe(): " + child.describe());
        System.out.println("parentView.describe(): " + parentView.describe());
        child.printBothFields();
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 FieldHidingDemo.java
java FieldHidingDemo
~~~

Stdout:

~~~text
child.label: child
parentView.label: parent
child.describe(): Child.describe
parentView.describe(): Child.describe
this.label: child
super.label: parent
~~~

Cùng một object `Child` được tham chiếu qua biến `child` kiểu `Child` và biến `parentView` kiểu `Parent`. Khi đọc `child.label`, trình biên dịch chọn field thuộc `Child`; khi đọc `parentView.label`, nó chọn field thuộc `Parent`. Đổi kiểu khai báo của tham chiếu ảnh hưởng **truy cập field** nhưng không làm thay đổi đối tượng runtime.

Trong `Child`:

- `this.label` chỉ field `Child.label`.
- `super.label` chỉ field `Parent.label`.
- `describe()` là instance method được **override**. Cả `child.describe()` và `parentView.describe()` đều chạy phiên bản `Child.describe()`.

Đây là khác biệt quan trọng giữa field và method trong Java. **Field không được override theo cơ chế dynamic dispatch.** Khi dùng cùng tên field ở superclass và subclass, hãy cân nhắc đổi tên hoặc hạn chế field thành `private`, cung cấp phương thức phù hợp để tránh nhầm lẫn.

### Quy tắc truy cập vẫn áp dụng

Trong ví dụ, `Parent.label` có package-private access, và `Child` được khai báo cùng phạm vi package/nested class nên câu lệnh truy cập là hợp lệ. Nếu đổi `Parent.label` sang `private` trong một thiết kế khác, subclass thông thường không được quyền đọc trực tiếp qua `super.label`; cần dùng API mà superclass cung cấp.

Kế thừa không phá vỡ quy tắc `private`. Đồng thời, Java còn có quy tắc về các class thuộc cùng *nest* có thể truy cập private member của nhau; đây là trường hợp khác với quyền truy cập của một subclass nằm độc lập.

### Trường `static` cũng có thể bị che khuất

Trong kế thừa, `static` field ở subclass có cùng tên với field thích hợp ở superclass có thể hide field ở superclass, và cũng được chọn theo tên class/kiểu tham chiếu trong biểu thức. Để code dễ hiểu, truy cập static field bằng **tên class khai báo** như `Parent.category`, `Child.category`, thay vì truy cập qua biến object.

Không thể khai báo một static field và instance field **cùng tên trong chính cùng một class** rồi coi là hai field tách biệt. Việc cho phép field trùng tên ở **hai class của chuỗi kế thừa** khác với quy tắc tên trong cùng một thân class.

## 8. Class lồng nhau và cách phân biệt `this` với `Outer.this`

Một inner class có thể mang field trùng tên với field của enclosing class. Khi đó, `this.field` trong inner class chỉ field của inner object; `Outer.this.field` chỉ field của enclosing instance.

Tạo **`NestedNameDemo.java`**:

~~~java
public class NestedNameDemo {
    private String label = "outer";

    class Inner {
        private String label = "inner";

        void show(String label) {
            System.out.println("Parameter: " + label);
            System.out.println("Inner: " + this.label);
            System.out.println("Outer: " + NestedNameDemo.this.label);
        }
    }

    public static void main(String[] args) {
        NestedNameDemo outer = new NestedNameDemo();
        NestedNameDemo.Inner inner = outer.new Inner();
        inner.show("argument");
    }
}
~~~

~~~bash
javac -encoding UTF-8 NestedNameDemo.java
java NestedNameDemo
~~~

Stdout:

~~~text
Parameter: argument
Inner: inner
Outer: outer
~~~

Trong `show(String label)`, tên `label` đơn giản trỏ đến tham số; `this.label` trỏ đến field của `Inner`; `NestedNameDemo.this.label` trỏ đến field của `NestedNameDemo` đang bao quanh inner object.

**Không dùng `Outer.this` trong một static nested class** để tham chiếu tới instance của outer class: static nested class không tự gắn với enclosing instance theo cách của non-static inner class. Trường hợp bài toán không cần quan hệ instance bao ngoài, static nested class thường rõ ràng và đơn giản hơn.

## 9. Forward reference và thời điểm khởi tạo field

Scope của field trong class không đồng nghĩa với việc có thể tự do **đọc bằng tên đơn giản trước dòng khai báo trong một field initializer**. Java có quy tắc *illegal forward reference* để giảm lỗi phụ thuộc thứ tự khai báo.

Đoạn sau **cố ý không biên dịch**:

~~~java
class InvalidForwardReference {
    int first = second; // illegal forward reference
    int second = 10;
}
~~~

Ở initializer của `first`, tên `second` được viết không đủ điều kiện và tham chiếu tới instance field khai báo ở phía sau. Trong tình huống này, compiler báo `illegal forward reference`. Quy tắc còn có các chi tiết cụ thể cho static field, instance field, initializer block, tham chiếu bằng tên đơn giản, và vị trí nằm bên trái phép gán; đừng diễn giải đơn giản rằng “không được đề cập tới bất kỳ field nào khai báo sau”.

Ví dụ **hợp lệ nhưng dễ gây lỗi logic**:

~~~java
class QualifiedForwardReference {
    int first = this.second;
    int second = 10;
}
~~~

Ở thời điểm initializer `first` chạy, `second` vẫn đang ở giá trị mặc định `0`. Biểu thức `this.second` là tham chiếu có qualification nên hợp lệ trong trường hợp này; sau đó initializer của `second` mới gán 10. Vì vậy một instance mới có `first == 0` và `second == 10`. **Hợp lệ về cú pháp không có nghĩa hợp lý về thiết kế.**

Ví dụ chạy độc lập để kiểm chứng, lưu **`InitializationOrderDemo.java`**:

~~~java
public class InitializationOrderDemo {
    static final class Pair {
        int first = this.second;
        int second = 10;

        int first() {
            return first;
        }

        int second() {
            return second;
        }
    }

    public static void main(String[] args) {
        Pair pair = new Pair();
        System.out.println("first=" + pair.first());
        System.out.println("second=" + pair.second());
    }
}
~~~

~~~bash
javac -encoding UTF-8 InitializationOrderDemo.java
java InitializationOrderDemo
~~~

Stdout:

~~~text
first=0
second=10
~~~

Một thiết kế tốt nên tránh đọc field trước khi field ấy được khởi tạo có chủ đích. Đặt các field initializer theo thứ tự dễ hiểu, hoặc thực hiện khởi tạo trạng thái phụ thuộc lẫn nhau trong constructor một cách rõ ràng.

### Static initializer, instance initializer và constructor

Trình tự khởi tạo trong Java có chi tiết về superclass, static initialization, instance field initializers, instance initializer blocks và constructor:

1. Khi class cần được khởi tạo theo quy tắc JVM, các static field initializer và static initializer block của class được thực hiện theo thứ tự văn bản tương ứng, sau những bước khởi tạo superclass thích hợp.
2. Khi tạo instance, trước hết các field của object có giá trị mặc định; sau đó quá trình khởi tạo liên quan đến superclass và các bước instance initialization/constructor được thực hiện theo các quy tắc của Java.
3. Trong cùng một class, instance field initializer và instance initializer block được thực hiện theo thứ tự xuất hiện trong mã nguồn, tại điểm thích hợp của quá trình constructor.
4. Constructor cuối cùng hoàn tất trạng thái. Nếu constructor gọi method có thể bị override trước khi subclass khởi tạo xong, method đó có thể quan sát field subclass ở giá trị mặc định — một mẫu thiết kế nên tránh.

Học phần “scope” cần phân biệt **thứ tự khởi tạo** với **phạm vi của tên**. Việc compiler có thể xác định field nào được tham chiếu không bảo đảm field đó đã có giá trị thiết kế mong muốn tại thời điểm đọc.

## 10. Phạm vi tên không quyết định thời điểm giải phóng tài nguyên

Không nên dùng trực giác “ra khỏi dấu ngoặc nhọn = mọi thứ bên trong bị hủy ngay”.

Xem đoạn minh họa đặt trong một phương thức:

~~~java
CourseProgress saved;

{
    CourseProgress temporary = new CourseProgress("Core");
    saved = temporary;
}

// Tên temporary đã ra khỏi scope.
// Object vẫn được tham chiếu qua saved.
~~~

Biến cục bộ `temporary` hết phạm vi sau dấu `}`. Tuy nhiên object mà nó từng tham chiếu vẫn có thể được truy cập qua `saved`. Với chương trình Java hợp lệ, compiler kiểm tra `saved` đã được gán trước khi đọc; ví dụ này gán `saved` trong block trước khi dùng.

Tương tự, phương thức tạo object và **trả tham chiếu** cho caller có thể làm object tiếp tục được sử dụng sau khi method kết thúc:

~~~java
static CourseProgress createProgress() {
    CourseProgress local = new CourseProgress("Java");
    return local;
}
~~~

Đây là đoạn method minh họa, yêu cầu có class `CourseProgress` phù hợp trong chương trình. `local` là biến cục bộ và hết phạm vi sau method, nhưng đối tượng có thể được caller giữ lại qua giá trị trả về.

### Tài nguyên ngoài heap cần được đóng rõ ràng

Việc object không còn được tham chiếu không đồng nghĩa file, socket hoặc connection của hệ điều hành được đóng tại thời điểm bạn mong muốn. Với các tài nguyên triển khai `AutoCloseable`, dùng **try-with-resources** để đóng đúng vòng đời thao tác:

~~~java
// Đoạn minh họa, đặt trong method có throws IOException:
try (java.io.BufferedReader reader =
         java.nio.file.Files.newBufferedReader(path)) {
    System.out.println(reader.readLine());
}
~~~

Ví dụ này yêu cầu biến `path` có kiểu `java.nio.file.Path`, và xử lý/khai báo `IOException`; không phải chương trình độc lập. Mục đích là phân biệt **kết thúc phạm vi một tên biến** với **đóng tài nguyên hữu hạn**. Nội dung I/O chi tiết nên học trong phần Java I/O; ở đây chỉ cần nhớ GC không thay thế việc đóng tài nguyên có chủ đích.

## 11. Biến được capture và `effectively final`: một ranh giới scope đáng chú ý

Local class, anonymous class và lambda có thể dùng một số biến cục bộ từ phạm vi bao ngoài nếu biến đó là **final hoặc effectively final**. “Effectively final” nghĩa là biến không được gán lại sau khi được gán giá trị theo quy tắc phân tích của compiler.

Ví dụ chạy độc lập, lưu **`CaptureScopeDemo.java`**:

~~~java
public class CaptureScopeDemo {
    private int base = 10;

    Runnable makeTask() {
        int bonus = 3; // Effectively final

        return () -> {
            System.out.println(base + bonus);
        };
    }

    public static void main(String[] args) {
        CaptureScopeDemo demo = new CaptureScopeDemo();
        Runnable task = demo.makeTask();
        task.run();
    }
}
~~~

~~~bash
javac -encoding UTF-8 CaptureScopeDemo.java
java CaptureScopeDemo
~~~

Stdout:

~~~text
13
~~~

Sau khi `makeTask()` trả về, `bonus` không còn có một tên cục bộ để mã caller truy cập. Tuy nhiên lambda vẫn có thể sử dụng **giá trị đã capture** của `bonus`. Đồng thời lambda có thể tham chiếu field `base` thông qua enclosing instance được capture theo nhu cầu. Đừng kết luận rằng một local variable phải tiếp tục tồn tại trong một frame stack như lúc method đang chạy; compiler/runtime có thể biểu diễn giá trị capture theo cách khác mà vẫn giữ đúng ngữ nghĩa Java.

Nếu thêm `bonus++;` sau khi đã khai báo, ví dụ trên sẽ không biên dịch do `bonus` không còn effectively final. Với field `base`, Java không áp dụng quy tắc effectively final tương tự; field có thể mutable, vì vậy lambda dùng field có thể quan sát giá trị đã cập nhật của object khi chạy.

## 12. Quy tắc phân giải tên trong code review: nhìn từ gần ra xa

Khi thấy một tên đơn giản như `value`, đừng đoán vội nó là field. Hãy kiểm tra theo ngữ cảnh:

1. Trong biểu thức có khai báo tham số/biến cục bộ tên `value` đang có hiệu lực không? Nếu có, tên đơn giản thường trỏ đến khai báo gần đó.
2. Nếu không, class hiện tại có field `value` không? Tên có thể biểu thị field instance/static tùy ngữ cảnh và quy tắc shadowing.
3. Nếu không, field kế thừa từ superclass hoặc field có thể truy cập từ enclosing class có thể liên quan.
4. Nếu cần đọc đúng field của **instance hiện tại**, dùng `this.value` trong instance context.
5. Nếu cần field của **superclass**, dùng `super.value` trong ngữ cảnh và quyền truy cập phù hợp.
6. Nếu cần static field, ưu tiên `ClassName.value` để người đọc biết đó là trạng thái cấp class.
7. Nếu tên bị che bởi một khai báo nhưng field của object khác mới là mục tiêu, dùng `object.value` khi field đó có thể truy cập.
8. Nếu trình biên dịch báo lỗi, đọc thông báo cụ thể trước khi đổi modifier hoặc thêm `static` một cách tùy tiện.

Các quy tắc chi tiết của Java có thêm sự tương tác với type names, local classes, imports và inheritance. Với bài học về field, cách làm thực tế là **tìm khai báo chính xác**, kiểm tra scope và quyền truy cập, rồi chỉ rõ object/class sở hữu field đó.

### Cách đặt tên giúp hạn chế che khuất không chủ ý

- Dùng tên field mô tả vai trò, ví dụ `remainingSeats`, `customerName`, `createdCount`.
- Sử dụng `this.field = field;` nhất quán trong constructor khi tham số trùng field; đây là mẫu Java phổ biến, rõ ý.
- Dùng `ClassName.staticField` thay cho `instance.staticField`.
- Tránh khai báo field subclass trùng tên field superclass nếu không có lý do thiết kế rõ ràng.
- Trong method dài, hạn chế reuse cùng một tên biến với nhiều ý nghĩa, dù compiler cho phép ở các block không chồng lấp.
- Đừng dùng `private`/getter/setter chỉ nhằm làm biến mất cảnh báo; hãy xác định ai cần quyền đọc và ai cần quyền thay đổi state.

## 13. Các lỗi và nhầm lẫn thường gặp

| Dấu hiệu / phát biểu | Nguyên nhân hoặc cách hiểu chính xác |
| --- | --- |
| Constructor chạy nhưng field vẫn `null` | Có thể viết `name = name;` và tự gán tham số thay vì `this.name = name;`. |
| `non-static variable ... cannot be referenced from a static context` | Đang truy cập instance field qua class hoặc từ static context không có instance. |
| `cannot find symbol` khi dùng biến sau dấu `}` | Tên biến cục bộ không còn trong scope đó. |
| `variable ... is already defined` | Khai báo trùng local/parameter ở phạm vi chồng lấp; Java không cho phép kiểu shadowing này. |
| `illegal forward reference` | Đọc field bằng tên đơn giản từ initializer trước dòng khai báo trong trường hợp bị cấm. |
| `parentRef.field` khác `childRef.field` dù là cùng object | Field hiding: compiler chọn field theo kiểu tham chiếu được khai báo. |
| `parentRef.method()` gọi code subclass | Instance method được override và được phân phối động; cơ chế khác field. |
| “Biến cục bộ ra khỏi scope nên object bị hủy ngay” | Hết scope tên không bảo đảm thu hồi object; object có thể còn reachable và GC không có lịch cố định. |
| “Static field thuộc về object đầu tiên” | Static field thuộc class runtime, không thuộc riêng object đầu tiên. |
| “`final` field khiến cả object bất biến” | `final` không tự bảo đảm immutable của mọi dữ liệu được tham chiếu. |
| “Tên field được khai báo sau method nên method không đọc được” | Method body có thể tham chiếu field nằm sau; forward reference trong initializer là trường hợp khác. |
| “`System.gc()` sẽ thu hồi object ngay” | Đây chỉ là yêu cầu/gợi ý với JVM; không thể dùng làm bảo đảm về thời điểm thu hồi. |

## 14. Bài tập kiểm tra hiểu biết

### Bài 1: Một tên, hai biến

Cho đoạn class minh họa:

~~~java
class Box {
    int size = 4;

    void setSize(int size) {
        size = size;
    }
}
~~~

Nếu tạo `Box b = new Box();`, gọi `b.setSize(9)` rồi đọc `b.size` trong nơi được phép truy cập, kết quả vẫn là **4**. Hai tên `size` trong `size = size;` là **tham số**, còn field chưa được cập nhật. Hãy sửa thành `this.size = size;` và dự đoán kết quả mới là **9**.

### Bài 2: Phạm vi block

~~~java
class BlockExample {
    int points = 1;

    void run(boolean active) {
        if (active) {
            int points = 10;
            System.out.println(points);
        }
        System.out.println(points);
    }
}
~~~

Đây là **class minh họa**, cần có nơi gọi method để chạy. Với `run(true)`, hai dòng in là:

~~~text
10
1
~~~

Lần in trong block dùng local `points`; lần in sau block dùng field `points`. Field không đổi. Với `run(false)`, chỉ có một dòng `1`.

### Bài 3: Field hiding so với method overriding

Dựa trên `FieldHidingDemo`, hãy thay `Parent parentView = child;` bằng `Child childView = child;` rồi đọc `childView.label`. Nó cho **`child`** vì kiểu tham chiếu là `Child`; việc tạo một biến tham chiếu mới không tạo object mới. Nếu ép kiểu hợp lệ `((Parent) child).label`, kết quả là **`parent`**, mặc dù object runtime vẫn là Child.

### Bài 4: Tư duy lifetime

~~~java
class Container {
    static Object shared;

    static void save() {
        Object local = new Object();
        shared = local;
    }
}
~~~

Sau khi `save()` trả về, tên local `local` không còn scope, nhưng object đã tạo còn có thể được tham chiếu qua `Container.shared`. Nếu đặt `Container.shared = null`, object **có thể** trở nên không reachable nếu không còn đường tham chiếu nào khác; không có bảo đảm thu hồi ngay. Đây là bài về tham chiếu và khả năng sống của object, không phải cách yêu cầu GC.

### Bài 5: Thêm bài kiểm tra vào chương trình

Trong `FieldShadowingDemo`, thêm dòng dưới đây ở cuối `main`:

~~~java
if (counter.current() != 8) {
    throw new AssertionError("Field value must be 8");
}
~~~

Đó là **đoạn bổ sung**, không phải một tệp riêng. Nếu không có lỗi, lệnh không in gì. Tiếp theo cố ý đổi constructor từ `this.value = value;` thành `value = value;`; giá trị field sau đó bắt đầu từ 10, rồi được cộng 3 thành 13, khiến kiểm tra ném `AssertionError`. Đây là một cách tự quan sát lỗi shadowing bằng kiểm tra trạng thái mong đợi.

## 15. Checklist áp dụng vào class thực tế

- [ ] Phân biệt được field, parameter và local variable chỉ bằng vị trí khai báo.
- [ ] Biết field instance còn thuộc object sau khi method kết thúc; local variable không trở thành field.
- [ ] Biết static field là dữ liệu thuộc class runtime, không thuộc riêng mỗi object.
- [ ] Không đồng nhất “ra khỏi scope” với “object được GC ngay”.
- [ ] Biết tham số/biến cục bộ có thể che khuất field, và dùng `this.field` khi cần.
- [ ] Biết Java cấm trùng tên các local/parameter khi phạm vi chồng lấp.
- [ ] Biết vì sao `this.field`, `super.field` và `ClassName.staticField` có thể khác nhau.
- [ ] Giải thích được field hiding chọn theo kiểu biểu thức, còn method overriding thường dispatch theo object runtime.
- [ ] Phân biệt scope của field trong class với hạn chế forward reference ở field initializer.
- [ ] Chỉ ra được class/object nào thực sự sở hữu state đang được đọc hoặc cập nhật.
- [ ] Tự biên dịch và chạy `ScopeLifetimeDemo`, `FieldShadowingDemo`, `FieldHidingDemo`, `NestedNameDemo` và `InitializationOrderDemo`.
- [ ] Tự viết được constructor tránh lỗi `field = field` và dự đoán kết quả trước khi chạy chương trình.

Một quy tắc thực hành có ích là khi đọc bất kỳ biểu thức nào chứa field, hãy trả lời theo thứ tự: **“Tên này đang được phân giải tới khai báo nào? Field này thuộc object hay class nào? Giá trị được tạo và có thể thay đổi ở thời điểm nào?”**. Ba câu trả lời đó giải quyết phần lớn lỗi về phạm vi, lifetime và che khuất tên trong Java.
