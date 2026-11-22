# Khai báo trường: kiểu dữ liệu, tên và giá trị ban đầu trong Java

## Mục tiêu

Sau bài này, bạn có thể:

- Nhận diện **trường dữ liệu** (*field*) trong khai báo lớp Java và phân biệt với biến cục bộ, tham số, thuộc tính được tính toán.
- Viết khai báo trường đúng cú pháp: **modifier**, **kiểu**, **tên**, **biểu thức khởi tạo tùy chọn**.
- Chọn kiểu nguyên thủy, kiểu tham chiếu, mảng và kiểu tham số hóa phù hợp; đặt tên và giới hạn quyền truy cập hợp lý.
- Giải thích giá trị mặc định của trường khi không có initializer; phân biệt với biến cục bộ vốn phải được gán trước khi đọc.
- Hiểu lúc nào initializer, khối khởi tạo và constructor được thực thi; dùng `this` để phân biệt trường với tham số trùng tên.
- Áp dụng `final`, `static` và tránh các lỗi thường gặp như sử dụng `var` cho field, đọc biến chưa khởi tạo, dùng chung đối tượng có thể thay đổi ngoài ý muốn.

## 1. Trường dữ liệu là gì?

**Field** là biến được khai báo trực tiếp trong phần thân một lớp hoặc một kiểu có hỗ trợ trường tương ứng, ở ngoài các phương thức và constructor. Field thuộc **đối tượng** (instance field) hoặc **lớp** (static field), tùy có từ khóa `static` hay không.

Ví dụ đoạn khai báo trong một lớp:

~~~java
public class Book {
    private String title;
    private int pages = 120;
    private boolean available = true;
    private static int totalBooks;
}
~~~

Trong đoạn này:

- `title`, `pages`, `available` là **instance fields**: mỗi đối tượng `Book` có các trường tương ứng của riêng mình.
- `totalBooks` là **static field**: trường gắn với lớp `Book`, không được tạo một bản riêng trong từng đối tượng.
- `private` là mức truy cập. Nó giúp hạn chế mã bên ngoài lớp tự ý thay đổi trạng thái.
- Kiểu dữ liệu quyết định tập giá trị hợp lệ cho trường: `String` là kiểu tham chiếu; `int` và `boolean` là kiểu nguyên thủy.
- `= 120` và `= true` là **field initializer**, tức biểu thức cung cấp giá trị khi đối tượng/lớp được khởi tạo.
- `title` và `totalBooks` không có initializer tường minh; chúng vẫn được Java **khởi tạo mặc định** theo quy tắc dành cho fields.

Biến được khai báo **bên trong** phương thức, constructor hoặc block là **biến cục bộ** (*local variable*), không phải field:

~~~java
public class Example {
    private int total;  // field

    public void add(int amount) {  // amount là tham số
        int extra = 2;             // extra là biến cục bộ
        total += amount + extra;   // dùng field total
    }
}
~~~

`total` tồn tại như phần trạng thái của đối tượng; `extra` chỉ thuộc phạm vi thực thi khối phương thức. Java không cho khai báo hai biến cục bộ cùng tên trong cùng phạm vi lồng không hợp lệ, còn trường và tham số cùng tên có thể tồn tại và được phân biệt bằng `this`.

## 2. Cú pháp khai báo một field

Cấu trúc cơ bản:

~~~text
[modifier ...] KiểuDuLieu tenTruong [= bieuThucKhoiTao];
~~~

Ví dụ:

~~~java
private int age;
private String fullName = "Chưa có tên";
public static final int MAX_ITEMS = 100;
~~~

Giải nghĩa thành phần:

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Modifier truy cập | Giới hạn nơi có thể sử dụng trường | `private`, `protected`, `public` hoặc không ghi |
| Modifier khác | Điều chỉnh đặc tính của trường | `static`, `final`, và một số modifier chuyên biệt |
| Kiểu dữ liệu | Quy định kiểu giá trị trường có thể giữ | `int`, `double`, `String`, `int[]`, `List<String>` |
| Tên trường | Định danh hợp lệ để tham chiếu tới field | `age`, `fullName`, `MAX_ITEMS` |
| Initializer | Biểu thức tùy chọn cung cấp giá trị ban đầu | `= 18`, `= "Java"`, `= new int[3]` |
| Dấu `;` | Kết thúc câu khai báo | Bắt buộc ở cuối field declaration |

Nếu không có modifier truy cập, trường có quyền **package-private**, tức mã khác trong cùng package có thể truy cập theo quy tắc ngôn ngữ; subpackage là package khác. Field không nhất thiết phải có initializer, nhưng **phải có tên và kiểu hợp lệ**, trừ cú pháp đặc biệt ngoài phạm vi như một số khai báo enum/record.

### 2.1. Chọn tên trường

Quy ước Java thường dùng `lowerCamelCase` cho field: `studentName`, `createdAt`, `quantity`; dùng `UPPER_SNAKE_CASE` cho hằng số có ngữ nghĩa cố định, thường là `static final`: `MAX_RETRIES`, `DEFAULT_PORT`.

Tên phải là **identifier hợp lệ**: không bắt đầu bằng chữ số, không chứa dấu gạch nối `-`, không dùng từ khóa `class`, `int`, `new`, v.v. Java phân biệt chữ hoa/chữ thường, nên `score` và `Score` là hai tên khác nhau. Dù cú pháp có cho phép nhiều kiểu tên Unicode và dấu `_`, trong mã nguồn thực tế nên chọn tên thể hiện trách nhiệm và dùng quy ước nhất quán.

### 2.2. Khai báo nhiều field cùng một kiểu

Cú pháp này hợp lệ:

~~~java
private int x, y;
private int width = 10, height = 20;
~~~

Hai khai báo đầu tạo **hai field** `x`, `y` có kiểu `int`; dòng sau khai báo `width = 10`, `height = 20`. Initializer **chỉ gắn với biến được viết ngay trước dấu `=`**, không tự áp dụng cho những tên khác.

Ví dụ:

~~~java
int a, b = 5;
~~~

Nếu là **field** thì `a` được khởi tạo mặc định bằng `0`, còn `b` bằng `5`. Nếu đặt khai báo này trong một method, đọc `a` trước khi gán sẽ bị lỗi biên dịch vì biến cục bộ không được tự động gán giá trị mặc định.

Để rõ ràng và dễ thêm chú thích hoặc modifier sau này, nên viết **mỗi field trên một dòng** khi chúng có ý nghĩa riêng.

## 3. Chọn kiểu dữ liệu cho field

Một field phải có **kiểu khai báo** (*declared type*). Các nhóm thường gặp:

| Kiểu | Ví dụ field | Giá trị biểu diễn |
| --- | --- | --- |
| `byte`, `short`, `int`, `long` | `private long fileSize = 1000L;` | Số nguyên trong khoảng giá trị của kiểu |
| `float`, `double` | `private double temperature = 36.5;` | Số thực dấu chấm động |
| `boolean` | `private boolean active = false;` | `true` hoặc `false` |
| `char` | `private char grade = 'A';` | Một đơn vị mã UTF-16 |
| Kiểu lớp/tham chiếu | `private String name = "An";` | Tham chiếu tới đối tượng hoặc `null` |
| Mảng | `private int[] scores = new int[3];` | Tham chiếu tới một đối tượng mảng hoặc `null` |
| Interface/generic | `private java.util.List<String> tags = new java.util.ArrayList<>();` | Tham chiếu tới đối tượng có kiểu tương thích |

Cách chọn kiểu phải phù hợp dữ liệu: `int` cho số lượng trong phạm vi hợp lý; `long` cho số đếm lớn; `boolean` cho cờ trạng thái; `String` cho chuỗi; `List<String>` cho danh sách nhãn. Các kiểu nguyên thủy **không chấp nhận `null`**, còn kiểu tham chiếu thông thường có thể nhận `null`.

Đối với tiền tệ cần độ chính xác thập phân, `double` có thể không phù hợp vì biểu diễn dấu chấm động nhị phân. Chẳng hạn có thể dùng `java.math.BigDecimal` với giá trị khởi tạo tường minh:

~~~java
private java.math.BigDecimal price = new java.math.BigDecimal("19.90");
~~~

Đây là **dòng khai báo field minh họa**, đặt bên trong một class. Việc chọn `BigDecimal` cho dữ liệu tiền tệ là quyết định mô hình dữ liệu; bản thân từ khóa khai báo field không quyết định quy tắc làm tròn.

### 3.1. Cần chú ý literal và phép chuyển kiểu

Java kiểm tra kiểu của biểu thức khởi tạo tại thời điểm biên dịch:

~~~java
private int quantity = 12;
private long distance = 9_000_000_000L;
private float rate = 0.5f;
private double ratio = 0.5;
private char symbol = 'J';
private String label = "Java";
~~~

Các ký tự `L` và `f` lần lượt tạo literal `long` và `float`. Nếu dùng `9_000_000_000` không có hậu tố `L`, literal số nguyên vượt miền `int` và không hợp lệ. Số thực dạng `0.5` mặc định là `double`, nên phép gán trực tiếp cho `float` thường cần `f` hoặc chuyển kiểu tường minh phù hợp.

Một số phép gán hằng số nguyên có thể dùng chuyển đổi thu hẹp được Java cho phép khi hằng nằm trong miền của kiểu, ví dụ `byte b = 100;`; nhưng `byte b = 200;` không biên dịch vì vượt phạm vi `byte`.

Không dùng `var` để khai báo field. **Local variable type inference** với `var` chỉ dành cho các ngữ cảnh biến cục bộ được phép của Java, ví dụ `var count = 1;` bên trong method; đối với field, bạn phải viết kiểu cụ thể:

~~~java
// Sai khi đặt ở cấp class:
// private var count = 1;

// Đúng ở cấp class:
private int count = 1;
~~~

## 4. Giá trị mặc định khi không khai báo initializer

Khi tạo một đối tượng, các **instance fields** được gán giá trị mặc định trước khi thực hiện các initializer tường minh/khối khởi tạo và constructor theo trình tự của Java. Các **static fields** cũng được gán giá trị mặc định khi lớp được chuẩn bị, trước giai đoạn chạy các static initializers tương ứng.

Bảng giá trị mặc định của **field**:

| Kiểu field | Giá trị mặc định |
| --- | --- |
| `byte`, `short`, `int` | `0` |
| `long` | `0L` |
| `float` | `0.0f` |
| `double` | `0.0d` |
| `boolean` | `false` |
| `char` | `'\\u0000'` (giá trị mã `0`) |
| Mọi kiểu tham chiếu, bao gồm `String`, mảng và interface | `null` |

Ví dụ, `String name;` không có nghĩa là chuỗi rỗng `""`; giá trị ban đầu của field là `null`. `int[] values;` không tự tạo mảng rỗng; muốn có đối tượng mảng phải khởi tạo, chẳng hạn `new int[0]` hoặc `new int[3]`. Với `new int[3]`, bản thân ba **phần tử của mảng** là các số `0` theo quy tắc mặc định dành cho thành phần mảng.

Giá trị mặc định không luôn là **giá trị hợp lệ theo nghiệp vụ**. Ví dụ `price = 0` có thể không phù hợp khi giá phải lớn hơn 0, còn `name = null` có thể gây `NullPointerException` nếu sử dụng như một chuỗi không null. Vì vậy hãy khởi tạo tường minh hoặc kiểm tra đầu vào trong constructor khi cần điều kiện bất biến.

### 4.1. Field khác biến cục bộ

Ví dụ:

~~~java
public class DefaultsVsLocals {
    int field; // Mặc định 0

    void demo() {
        int local;
        // System.out.println(local); // Lỗi: biến cục bộ chưa được gán
        local = 7;
        System.out.println(field + local);
    }

    public static void main(String[] args) {
        new DefaultsVsLocals().demo();
    }
}
~~~

Lưu trong **`DefaultsVsLocals.java`**, chạy:

~~~bash
javac DefaultsVsLocals.java
java DefaultsVsLocals
~~~

Output:

~~~text
7
~~~

Compiler cho phép đọc `field` vì Java gán mặc định `0`. Biến `local` được gán `7` trước lần đọc. Nếu bỏ chú thích trước `System.out.println(local);`, chương trình sẽ **không biên dịch** do vi phạm quy tắc gán chắc chắn (*definite assignment*).

## 5. Ví dụ đầy đủ: kiểu, tên, giá trị ban đầu, `static` và `final`

Tệp **`FieldDeclarationDemo.java`** dưới đây có thể biên dịch/chạy với JDK 17 trở lên, không cần thư viện ngoài.

~~~java
public class FieldDeclarationDemo {
    static final class Defaults {
        int number;         // 0
        boolean enabled;    // false
        char initial;       // ký tự có mã 0
        String text;        // null
        int[] values;       // null
    }

    static final class Item {
        private final String id;          // Được gán trong constructor
        private String title = "Chưa đặt tên";
        private int quantity;             // Mặc định 0
        private double price = 12.5;
        private boolean active = true;
        private String note;              // Mặc định null
        private int[] monthly = new int[2];

        private static int createdCount;       // Dùng chung trong lớp Item
        private static final int MAX_QUANTITY = 100;

        Item(String id, String title, int quantity) {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("id must not be blank");
            }
            if (quantity < 0 || quantity > MAX_QUANTITY) {
                throw new IllegalArgumentException("invalid quantity");
            }
            this.id = id;
            this.title = title;
            this.quantity = quantity;
            createdCount++;
        }

        String description() {
            return id + " | " + title
                    + " | qty=" + quantity
                    + " | price=" + price
                    + " | active=" + active
                    + " | note=" + note
                    + " | month0=" + monthly[0];
        }

        static int createdCount() {
            return createdCount;
        }
    }

    static final class InitializationOrder {
        int first = 1;
        int second = first + 2;

        {
            first = 10;
        }

        InitializationOrder() {
            second = first + 5;
        }
    }

    public static void main(String[] args) {
        Defaults defaults = new Defaults();
        System.out.println("defaults: int=" + defaults.number
                + ", bool=" + defaults.enabled
                + ", charCode=" + (int) defaults.initial
                + ", text=" + defaults.text
                + ", values=" + defaults.values);

        Item first = new Item("SKU1", "Bút", 3);
        Item second = new Item("SKU2", "Vở", 0);

        System.out.println(first.description());
        System.out.println(second.description());
        System.out.println("created=" + Item.createdCount()
                + ", max=" + Item.MAX_QUANTITY);

        InitializationOrder order = new InitializationOrder();
        System.out.println("order: first=" + order.first
                + ", second=" + order.second);
    }
}
~~~

Chạy trong thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 FieldDeclarationDemo.java
java FieldDeclarationDemo
~~~

Output chính xác:

~~~text
defaults: int=0, bool=false, charCode=0, text=null, values=null
SKU1 | Bút | qty=3 | price=12.5 | active=true | note=null | month0=0
SKU2 | Vở | qty=0 | price=12.5 | active=true | note=null | month0=0
created=2, max=100
order: first=10, second=15
~~~

**Giải thích:**

1. Các field trong `Defaults` không có initializer nên bắt đầu bằng giá trị mặc định. Để nhìn thấy `char` mặc định vô hình, chương trình ép sang `int` và in giá trị mã `0`.
2. Các field `price`, `active`, `title`, `monthly` của `Item` được khởi tạo tường minh. Riêng `monthly` là mảng hai phần tử; `monthly[0]` có giá trị `0`.
3. `title` ban đầu là `"Chưa đặt tên"`, rồi bị constructor gán bằng tên được truyền vào. Giá trị quan sát sau khi tạo đối tượng là `"Bút"` hoặc `"Vở"`.
4. `id` có `final` và không có initializer ngay tại khai báo; mỗi constructor hợp lệ đều phải gán trường này đúng quy tắc trước khi hoàn tất.
5. Hai đối tượng `Item` có các trường thực thể riêng. Trong khi đó `createdCount` là trường `static`, nên cả hai lần gọi constructor tăng chung một bộ đếm.
6. `MAX_QUANTITY` vừa `static` vừa `final`, biểu diễn giới hạn cố định của lớp. Không thể gán lại field này sau khởi tạo.
7. Trong `InitializationOrder`, lần lượt gán `first = 1`, `second = 3`, thực thi instance initializer block làm `first = 10`, rồi constructor gán `second = 15`. Vì vậy output cuối cùng là `first=10, second=15`.

Ví dụ minh họa quy tắc ngôn ngữ, không buộc bạn lúc nào cũng dùng khối khởi tạo hay các trường `static`. Với mã ứng dụng thông thường, constructor và initializer ngay tại khai báo thường dễ đọc hơn khi không có yêu cầu đặc biệt.

## 6. Thời điểm khởi tạo: field initializer, instance initializer, constructor

Khai báo có initializer không đồng nghĩa với việc biểu thức đã được chạy ngay khi compiler đọc tệp nguồn. Các bước chính cần hiểu:

1. **Đối tượng mới**: Java cấp phát đối tượng, gán giá trị mặc định cho các instance fields; nếu có kế thừa, quy tắc khởi tạo lớp cha được áp dụng trước phần khởi tạo tương ứng của lớp con.
2. **Initializer cho đối tượng**: trong một lớp, các biểu thức initializer của instance fields và các instance initializer blocks được thực thi theo **thứ tự văn bản** khi đến lượt khởi tạo phần của lớp đó.
3. **Constructor**: phần thân constructor thực thi sau khi hoàn tất các bước khởi tạo instance tương ứng; constructor có thể gán đè những field đã có initializer. Chuỗi gọi constructor `this(...)` hoặc lớp cha `super(...)` làm thứ tự cụ thể chi tiết hơn, nhưng không thay đổi ý nghĩa trường cuối cùng thuộc từng đối tượng.
4. **Static fields**: được khởi tạo mặc định trong quá trình chuẩn bị lớp; các static field initializers và static initializer blocks được thực thi theo thứ tự văn bản trong quá trình khởi tạo lớp theo quy tắc JVM. Chúng **không chạy lại mỗi lần gọi `new`**.

Ví dụ ngắn ở cùng một lớp:

~~~java
class Counter {
    static int seed = 10;   // Trường của lớp
    int value = 1;         // Trường của từng đối tượng

    Counter() {
        value = 5;
    }
}
~~~

Nếu tạo `new Counter()` thành công, giá trị `value` của đối tượng mới sau constructor là `5`, không phải `1`. Nếu tạo nhiều đối tượng, mỗi đối tượng có `value` riêng; `seed` là trường của lớp. Đây là đoạn khai báo minh họa, không có `main` để chạy độc lập.

**Thứ tự khai báo có thể quan trọng**: một initializer có thể đọc một field đã được khởi tạo sớm hơn; tham chiếu đơn giản tới field khai báo phía sau có thể gây lỗi `illegal forward reference` theo quy tắc Java. Ngay cả khi mã sử dụng một cách tham chiếu được compiler cho phép tới field chưa chạy initializer, giá trị đọc lúc đó có thể chỉ là giá trị mặc định. Để tránh lỗi khó hiểu, đừng thiết kế vòng phụ thuộc giữa các field initializers.

## 7. `this`: phân biệt tham số và field trùng tên

Xem ví dụ chạy độc lập **`FieldAssignmentDemo.java`**:

~~~java
public class FieldAssignmentDemo {
    static final class Point {
        private int x = 1;
        private int y;

        Point(int x, int y) {
            this.x = x;
            this.y = y;
        }

        void moveRight(int x) {
            this.x += x;
        }

        void print() {
            int x = 99;
            System.out.println("local=" + x
                    + ", field=" + this.x
                    + ", y=" + this.y);
        }
    }

    public static void main(String[] args) {
        Point p = new Point(4, 5);
        p.moveRight(3);
        p.print();
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac FieldAssignmentDemo.java
java FieldAssignmentDemo
~~~

Output:

~~~text
local=99, field=7, y=5
~~~

Trong `Point(int x, int y)`, `x` và `y` không có `this.` là **tham số**, còn `this.x` và `this.y` là **field của đối tượng hiện tại**. Viết `x = x;` chỉ gán lại tham số cho chính nó, không cập nhật field. Tương tự, `print()` có biến cục bộ `x = 99`, nhưng `this.x` vẫn giữ trạng thái thực của đối tượng: `4 + 3 = 7`.

Trong **static method**, không có `this`, vì phương thức không gắn với một đối tượng nhận lời gọi. Static fields thường được tham chiếu rõ ràng bằng `ClassName.fieldName`.

## 8. `final` và `static` khi khai báo field

Đây là hai modifier thường đi cùng khai báo trường, nhưng có ý nghĩa độc lập:

| Khai báo | Ý nghĩa |
| --- | --- |
| `int count;` | Instance field có thể gán lại |
| `final int id = 7;` | Instance field có giá trị được gán theo quy tắc `final`, không thể gán lại |
| `static int created;` | Static field có thể gán lại, dùng chung ở cấp lớp |
| `static final int LIMIT = 100;` | Static final field: một giá trị cố định sau khởi tạo của lớp |

Một **blank final field** là field `final` chưa có initializer ngay tại khai báo. Đối với blank final instance field, constructor phải đảm bảo field được gán đúng một lần trên các luồng hoàn tất bình thường theo quy tắc definite assignment; có thể gán qua instance initializer phù hợp. Với blank `static final`, việc gán thường diễn ra ở static initializer.

Ví dụ:

~~~java
class ConnectionSettings {
    private final String host;
    private final int port;

    ConnectionSettings(String host, int port) {
        this.host = host;
        this.port = port;
    }
}
~~~

Đây là khai báo lớp minh họa hợp lệ. Compiler kiểm tra hai field `final` được gán trước khi constructor kết thúc bình thường; dòng `this.host = host` phân biệt field với tham số.

**`final` không có nghĩa là đối tượng mà một field tham chiếu tới sẽ bất biến.** Ví dụ:

~~~java
private final java.util.List<String> tags = new java.util.ArrayList<>();
~~~

Đây là field declaration hợp lệ bên trong class. Không thể gán lại `tags = new ArrayList<>()` sau khi đã khởi tạo field, nhưng vẫn có thể gọi `tags.add("java")` nếu truy cập được danh sách. Tương tự, `static final` với một collection có thể thay đổi **không làm collection trở thành bất biến**. Nếu muốn dữ liệu bất biến, cần chọn kiểu/API và cách quản lý tham chiếu phù hợp.

**Quan trọng:** Field `static` là trạng thái chung; không nên biến mọi field thành `static` chỉ để dùng trong `main`. Field theo từng đối tượng mới giúp hai thực thể có trạng thái độc lập. Các trường `static` có thể thích hợp cho hằng số hoặc bộ đếm/đăng ký dùng chung có chủ ý; nếu nhiều luồng cùng cập nhật thì còn cần xét đồng bộ hóa.

## 9. Initializer với kiểu tham chiếu và trạng thái có thể thay đổi

Xét các khai báo field:

~~~java
private String title = "";
private int[] scores = new int[3];
private java.util.List<String> tags = new java.util.ArrayList<>();
~~~

Nếu là **instance fields**, mỗi lần tạo đối tượng của lớp thường chạy các biểu thức tạo mảng/danh sách mới, do đó mỗi đối tượng có mảng/danh sách riêng từ các initializer trên. `String` bất biến nên không gặp vấn đề sửa nội dung như collection mutable.

Ngược lại:

~~~java
private static final java.util.List<String> SHARED_TAGS =
        new java.util.ArrayList<>();
~~~

`SHARED_TAGS` là **một field static**, tham chiếu đến một danh sách có thể thay đổi được dùng chung trong lớp. `final` ngăn thay tham chiếu; không ngăn thay đổi nội dung danh sách. Nếu mỗi đối tượng đều thao tác lên danh sách đó, trạng thái của chúng có thể ảnh hưởng lẫn nhau.

Một nguồn chia sẻ khác là **gán tham chiếu từ bên ngoài**:

~~~java
class Basket {
    private final java.util.List<String> items;

    Basket(java.util.List<String> items) {
        this.items = items; // Giữ cùng tham chiếu với bên gọi
    }
}
~~~

Hai đối tượng `Basket` được truyền cùng một `List` sẽ có hai field `items` riêng nhưng cả hai chứa cùng tham chiếu. Để cách ly danh sách khi cần, có thể sao chép phòng vệ: `this.items = new java.util.ArrayList<>(items);`. Đây là **sao chép nông**: phần tử kiểu tham chiếu có thể vẫn được chia sẻ.

Nếu một field tham chiếu không được khởi tạo, nhớ kiểm tra `null` trước khi gọi phương thức hoặc khởi tạo đầy đủ qua constructor. Với trạng thái bắt buộc, constructor là nơi thường phù hợp để kiểm tra `null` bằng `java.util.Objects.requireNonNull(value, "value")` hoặc kiểm tra nghiệp vụ tương đương.

## 10. Những lỗi khai báo field hay gặp

| Vấn đề | Ví dụ/biểu hiện | Cách hiểu và khắc phục |
| --- | --- | --- |
| Quên dấu `;` | `private int age = 18` | Mỗi field declaration phải kết thúc bằng `;`. |
| Thiếu kiểu | `private name = "An";` | Viết `private String name = "An";`. |
| Dùng `var` ở cấp class | `private var score = 10;` | Field phải khai báo kiểu tường minh, ví dụ `private int score = 10;`. |
| Sai kiểu literal | `float ratio = 0.5;` | Dùng `0.5f` hoặc kiểu `double` tùy nhu cầu. |
| Vượt miền số nguyên | `byte level = 200;` | Chọn kiểu đủ rộng hoặc điều chỉnh giá trị hợp lệ. |
| Nhầm field và local | Đọc `int x;` bên trong method trước phép gán | Local không tự có giá trị mặc định; phải gán trước khi đọc. |
| Nhầm `null` với giá trị rỗng | `String name;` rồi `name.length()` | Field tham chiếu mặc định `null`; khởi tạo hoặc kiểm tra hợp lệ trước sử dụng. |
| Quên `this` khi trùng tên | `Person(String name) { name = name; }` | Gán `this.name = name;` để cập nhật field. |
| Gán lại `final` | `final int x = 1;` rồi `x = 2;` | `final` có quy tắc gán một lần; bỏ gán lại hoặc bỏ `final` nếu cần thay đổi. |
| Blank final thiếu gán | Constructor kết thúc mà chưa gán một field `final` | Gán nó trên mọi đường hoàn tất constructor theo quy tắc Java. |
| Cho rằng `static` là của từng object | `static int count;` nhưng mong mỗi object có bộ đếm riêng | Dùng instance field nếu trạng thái thuộc từng đối tượng. |
| Dùng `final` để “khóa” collection | `final List<String> list = new ArrayList<>();` | Chỉ tham chiếu là không gán lại được; nội dung collection vẫn mutable. |
| Khởi tạo theo thứ tự phụ thuộc sai | Initializer đọc field khác chưa chạy khởi tạo | Sắp xếp hợp lý và tránh vòng phụ thuộc giữa các field initializers. |
| Công khai trạng thái mutable | `public java.util.List<String> items;` | Cân nhắc `private`, kiểm soát thay đổi qua phương thức và sao chép khi cần. |

### Phân biệt khai báo và sử dụng

Khai báo `private int score;` vừa chỉ định tên, kiểu, quyền truy cập vừa tạo field tương ứng trên mỗi đối tượng; nó **không** tự tạo một đối tượng `Score` hay gọi phương thức nào. Khi gán `score = 8;`, giá trị của field thay đổi. Khi `private String owner = new String("An");` chạy ở initializer, biểu thức `new` mới thực sự tạo đối tượng `String` được tham chiếu. Không phải mọi initializer chứa biểu thức đều bắt buộc tạo đối tượng mới: ví dụ `= null`, `= 10`, `= existingReference` có ngữ nghĩa khác nhau.

Một initializer là biểu thức Java nên có thể gọi phương thức và gây side effect. Tuy nhiên, tránh những initializer phức tạp, phụ thuộc I/O hoặc trạng thái chưa sẵn sàng: điều đó làm khởi tạo đối tượng khó dự đoán và khó kiểm thử.

## 11. Câu hỏi ôn tập có lời giải

**Câu 1.** Cho đoạn khai báo cấp class:

~~~java
int a, b = 7;
String name;
boolean ready = true;
~~~

Sau khi tạo đối tượng thành công, các giá trị ban đầu là gì?  
**Đáp án:** `a = 0`, `b = 7`, `name = null`, `ready = true`. Chỉ `b` có initializer `7`; các field còn lại dùng giá trị mặc định hoặc initializer tương ứng.

**Câu 2.** Tại sao khai báo `private var age = 18;` trong lớp bị lỗi, dù `var age = 18;` có thể dùng trong method?  
**Đáp án:** `var` hỗ trợ suy luận kiểu cho những biến cục bộ được phép; field phải nêu kiểu trong khai báo, ví dụ `private int age = 18;`.

**Câu 3.** Field `private final String id;` có hợp lệ không khi chưa có `= ...`?  
**Đáp án:** Có. Đây là blank final field; constructor hoặc vị trí khởi tạo được phép phải gán field theo quy tắc definite assignment trước khi đối tượng khởi tạo hoàn tất bình thường.

**Câu 4.** `private int[] values = new int[2];` khác `private int[] values;` ra sao?  
**Đáp án:** Dạng đầu khởi tạo một mảng có độ dài 2, các phần tử `int` là `0`. Dạng sau chưa tham chiếu mảng nào, nên giá trị mặc định là `null`.

**Câu 5.** Vì sao trong `User(String name) { this.name = name; }` cần `this`?  
**Đáp án:** Tham số `name` che khuất field cùng tên. `this.name` xác định trường của đối tượng cần nhận giá trị từ tham số.

**Câu 6.** Hai đối tượng đều có `private static int count;`. Chúng có hai giá trị `count` độc lập không?  
**Đáp án:** Không. `static` khai báo trường thuộc lớp, dùng chung trong ngữ cảnh lớp; nếu cần giá trị theo từng đối tượng, bỏ `static`.

**Câu 7.** `private final List<String> items = new ArrayList<>();` có ngăn được `items.add("X")` không?  
**Đáp án:** Không. `final` ngăn gán lại tham chiếu field, không tự khiến `ArrayList` bất biến. Cần bảo vệ trạng thái bằng thiết kế API phù hợp nếu muốn ngăn sửa.

## Ghi nhớ

Khai báo field có cấu trúc **modifier + kiểu + tên + initializer tùy chọn + dấu chấm phẩy**. Field có giá trị mặc định hợp lệ theo loại dữ liệu dù không có initializer; điều đó **khác biến cục bộ**. Giá trị cuối sau khi tạo đối tượng còn phụ thuộc initializer, khối khởi tạo và constructor. Chọn kiểu phù hợp, đặt tên rõ, dùng `private` để đóng gói, dùng `final` cho field không cần gán lại, dùng `static` khi trạng thái thực sự thuộc lớp và kiểm soát tham chiếu tới đối tượng mutable để tránh chia sẻ dữ liệu ngoài ý muốn.
