# Tạo đối tượng và gọi phương thức bằng dấu chấm trong Java

> **Java core — language-basics / Lớp và đối tượng**  
> **Môi trường:** JDK 17+, một file Java tự chứa.  
> **Mục tiêu:** Tạo đối tượng bằng `new`, giữ tham chiếu trong biến, gọi phương thức bằng cú pháp `object.method(arguments)`, hiểu kết quả/`void`, trạng thái riêng từng đối tượng, alias, `null` và khác biệt giữa phương thức instance với `static`.

## 1. Từ lớp đến đối tượng

**Lớp** (*class*) khai báo trạng thái (trường) và hành vi (phương thức). **Đối tượng** (*object*) là một thực thể được tạo từ lớp đó. Câu lệnh `new Type(...)` thường cấp phát đối tượng và gọi **constructor** phù hợp để khởi tạo nó:

~~~java
class Lamp {
    private boolean on;

    Lamp(boolean initiallyOn) { // Constructor: tên giống lớp, không có kiểu trả về.
        this.on = initiallyOn;
    }

    void turnOn() {              // Phương thức instance.
        this.on = true;
    }

    boolean isOn() {             // Trả về trạng thái hiện tại.
        return this.on;
    }
}

// Sử dụng từ một phương thức phù hợp:
// Lamp deskLamp = new Lamp(false);
// deskLamp.turnOn();
// System.out.println(deskLamp.isOn()); // true.
~~~

Trong `Lamp deskLamp = new Lamp(false);`:

| Phần | Ý nghĩa |
| --- | --- |
| `Lamp` bên trái | Kiểu của biến tham chiếu |
| `deskLamp` | Tên biến giữ tham chiếu đến đối tượng |
| `new Lamp(false)` | Tạo đối tượng và gọi constructor nhận `boolean` |
| `deskLamp.turnOn()` | Gọi phương thức instance qua tham chiếu và dấu chấm |
| `deskLamp.isOn()` | Gọi phương thức rồi nhận giá trị `boolean` |

Constructor **không phải phương thức `void`**. Tên constructor trùng tên lớp và không khai báo kiểu trả về; không thể gọi lại nó bằng cú pháp `deskLamp.Lamp(...)`.

## 2. Dấu chấm `.` để gọi phương thức

Cú pháp thường gặp:

~~~java
receiver.methodName(argument1, argument2);
~~~

`receiver` là biểu thức tham chiếu tới đối tượng (như tên biến `deskLamp`). Dấu `.` chọn thành viên có thể truy cập; dấu ngoặc `(...)` và đối số thể hiện **lời gọi phương thức**.

~~~java
String text = " java ";
String clean = text.trim(); // "java"
int size = clean.length();  // 4.
boolean empty = clean.isEmpty(); // false.
~~~

Các phương thức này là instance method của `String`: mỗi lời gọi xác định đối tượng nhận lời gọi qua `text` hoặc `clean`. Trong khi đó, `text.length` (thiếu ngoặc) **không phải lời gọi hợp lệ** vì `String` cung cấp phương thức `length()` chứ không phải trường công khai `length`.

- `object.field`: truy cập **trường** nếu quyền truy cập cho phép.
- `object.method()`: gọi **phương thức không tham số**.
- `object.method(arg)`: gọi phương thức có tham số tương ứng.
- `method()` trong cùng lớp có thể là cách viết rút gọn trong ngữ cảnh phù hợp, nhưng viết `object.method()` giúp chỉ rõ **đối tượng nhận lời gọi**.

Nếu trường là `private`, mã ở một lớp không được cấp quyền không thể đọc/ghi trực tiếp `object.field`; hãy dùng phương thức công khai thích hợp thay vì tùy tiện làm trường `public`.

## 3. Phương thức có tham số, kiểu trả về và `void`

~~~java
class Counter {
    private int value;

    Counter(int start) {
        this.value = start;
    }

    void add(int amount) {
        this.value += amount;
    }

    int current() {
        return this.value;
    }
}

// Counter counter = new Counter(2);
// counter.add(3);          // Cập nhật giá trị, không trả giá trị.
// int now = counter.current(); // now == 5.
~~~

Khi gọi `counter.add(3)`, `3` là **đối số**, còn `amount` là **tham số** của phương thức `add`. `counter.current()` trả một giá trị `int` để gán, in hoặc dùng trong biểu thức:

~~~java
// System.out.println("now=" + counter.current());
// int doubleValue = counter.current() * 2;
~~~

`void` nghĩa là phương thức **không cung cấp giá trị trả về**; không thể viết `int x = counter.add(3);`. Ngược lại, kiểu trả về `int` cho phép lấy giá trị từ `current()`.

Trong thân phương thức instance, `this` chỉ **đối tượng hiện tại** đang nhận lời gọi. `this.value` rõ ràng là trường của đối tượng, không phải biến cục bộ cùng tên. Các đối số Java được truyền **theo giá trị**, kể cả khi giá trị là tham chiếu tới đối tượng.


## 4. Lời gọi qua dấu chấm chọn đúng receiver

~~~java
Counter first = new Counter(2);
Counter second = new Counter(5);
first.add(3);
second.add(-2);
// first.current() == 5; second.current() == 3.
~~~

Dấu chấm trong `first.add(3)` chọn object do `first` tham chiếu, còn `second.add(-2)` tác động trên object thứ hai. Hai lời gọi cùng method nhưng có **receiver** khác nhau nên thay đổi hai field `value` độc lập.

## 5. Alias và null ảnh hưởng thế nào đến lời gọi?

~~~java
Counter alias = first;
alias.add(1);                 // first.current() == 6.
alias = new Counter(1);       // Chỉ thay tham chiếu alias.
Counter missing = null;
// missing.add(1);            // NullPointerException nếu chạy.
~~~

`alias = first` sao chép giá trị tham chiếu, **không** gọi constructor. Khi hai tên chỉ cùng object, lời gọi qua tên nào cũng đến cùng trạng thái; gán lại `alias` không làm `first` đổi tham chiếu. Với `null`, không có object làm receiver để gọi instance method, nên phải kiểm tra hoặc bảo đảm tham chiếu khác null.

Để so xem hai tham chiếu có cùng object, dùng `==`; so sánh **nội dung nghiệp vụ** của hai object cần hợp đồng `equals` thích hợp. Bài đầu chương giải thích sâu hơn về object identity và alias; ở đây hãy tập trung vào receiver của từng lời gọi.

## 6. Gọi nối tiếp và biểu thức tạo đối tượng tạm

Vì `new Counter(...)` là biểu thức cho ra tham chiếu, có thể gọi phương thức ngay trên đối tượng mới:

~~~java
// new Counter(4).current()  // Trả 4.
~~~

Nếu một phương thức trả lại đối tượng hoặc một tham chiếu thích hợp, có thể **gọi nối tiếp** (*method chaining*):

~~~java
class Accumulator {
    private int total;

    Accumulator add(int number) {
        total += number;
        return this;
    }

    int value() {
        return total;
    }
}

// int result = new Accumulator().add(2).add(3).value();
// result == 5.
~~~

Phân giải từ trái sang phải theo chuỗi nhận kết quả: `new Accumulator()` tạo đối tượng, `add(2)` trả về `this`, `add(3)` cập nhật cùng đối tượng, rồi `value()` trả kết quả.

Nếu phương thức trả `void`, không thể nối tiếp bằng cách gọi một phương thức khác **trên giá trị trả về** của lời gọi `void`. Dùng tên biến đối tượng và gọi các lệnh riêng để rõ ràng khi cần.


## 7. Dấu chấm cũng xuất hiện ở lời gọi static

~~~java
Counter counter = new Counter(2);
int current = counter.current();       // Instance: có receiver Counter.
int maximum = Math.max(4, 9);        // Static: Math là tên lớp.
~~~

Cùng dấu `.`, nhưng `counter.current()` gọi hành vi trên instance, còn `Math.max(...)` gọi static method qua **tên lớp**, không cần object `Math`. Hãy ưu tiên `Type.staticMethod(...)` để tránh hiểu nhầm một biến object là receiver của phương thức static; bài chuyên đề `static` phân tích đầy đủ sự khác biệt.

## 8. Chương trình Java 17+ chạy độc lập

Tạo file **DotInvocationDemo.java**:

~~~java
public final class DotInvocationDemo {
    private static final class Counter {
        private final String label;
        private int value;

        Counter(String label, int start) {
            this.label = label;
            this.value = start;
        }

        void increment() {
            this.value++;
        }

        void add(int amount) {
            this.value += amount;
        }

        int current() {
            return this.value;
        }

        boolean isPositive() {
            return this.value > 0;
        }

        String summary() {
            return label + ":" + value;
        }

        Counter addAndReturn(int amount) {
            add(amount);
            return this;
        }

        static int recommendedStart() {
            return 1;
        }
    }

    public static void main(String[] args) {
        Counter first = new Counter("A", 2);
        Counter second = new Counter("B", 5);
        System.out.println("createdA=" + first.summary());
        System.out.println("createdB=" + second.summary());

        first.increment();
        first.add(3);
        second.add(-2);
        System.out.println("afterCallsA=" + first.summary());
        System.out.println("afterCallsB=" + second.summary());
        System.out.println("returnedValue=" + first.current());
        System.out.println("isPositive=" + first.isPositive());

        Counter alias = first;
        alias.increment();
        System.out.println("aliasSame=" + (alias == first));
        System.out.println("afterAlias=" + first.summary());

        Counter another = new Counter("A", 7);
        System.out.println("sameStateDifferentObject=" + (first == another));
        System.out.println("anotherSummary=" + another.summary());

        System.out.println("afterChain="
                + first.addAndReturn(2).addAndReturn(1).summary());
        System.out.println("temporary="
                + new Counter("T", 4).summary());

        alias = new Counter("X", 1);
        System.out.println("aliasAfterReassign=" + alias.summary());
        System.out.println("firstAfterReassign=" + first.summary());

        System.out.println("staticDefault=" + Counter.recommendedStart());
        System.out.println("mathMax=" + Math.max(4, 9));

        Counter missing = null;
        System.out.println("missingIsNull=" + (missing == null));
        try {
            missing.increment();
        } catch (NullPointerException ex) {
            System.out.println("nullCall=NullPointerException");
        }
    }
}
~~~

Biên dịch và chạy tại thư mục chứa file (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 DotInvocationDemo.java
java DotInvocationDemo
~~~

**Expected stdout chính xác:**

~~~text
createdA=A:2
createdB=B:5
afterCallsA=A:6
afterCallsB=B:3
returnedValue=6
isPositive=true
aliasSame=true
afterAlias=A:7
sameStateDifferentObject=false
anotherSummary=A:7
afterChain=A:10
temporary=T:4
aliasAfterReassign=X:1
firstAfterReassign=A:10
staticDefault=1
mathMax=9
missingIsNull=true
nullCall=NullPointerException
~~~

Hai đối tượng `first`/`second` có trạng thái độc lập. `aliasSame=true` nhưng `sameStateDifferentObject=false` chứng minh **alias khác với đối tượng mới có cùng trạng thái**. `afterChain` minh họa các phương thức trả về `this` cho phép gọi nối tiếp; `nullCall` chỉ lỗi khi gọi instance method qua tham chiếu `null`.

## 9. Lỗi thường gặp và bài tập

| Lỗi / hiểu nhầm | Cách hiểu hoặc sửa |
| --- | --- |
| Viết `Counter c; c.increment();` với local chưa khởi tạo | Tạo `new Counter(...)` hoặc gán tham chiếu hợp lệ trước khi dùng |
| Viết `Counter c = null; c.increment();` | Đối tượng chưa tồn tại; có thể gây `NullPointerException` |
| Gọi `c.current` thay vì `c.current()` | Phương thức phải có `(...)` kể cả khi không có đối số |
| Viết `int n = c.increment();` khi phương thức trả `void` | Không thể dùng lời gọi `void` làm giá trị |
| Tưởng `Counter alias = c` tạo object mới | Chỉ sao chép tham chiếu; dùng `new` khi cần đối tượng mới |
| Tưởng hai đối tượng cùng lớp luôn có chung trường instance | Mỗi đối tượng có giá trị trường instance riêng |
| Tưởng constructor được gọi bằng `c.Counter()` | Constructor chạy khi `new Counter(...)`, không phải method bình thường |
| Dùng `Math.max` như instance method | Gọi static bằng `Math.max(...)` |
| Truy cập trường `private` từ lớp khác | Dùng phương thức được cấp quyền, thiết kế getter/setter nếu cần |

**Bài 1.** Tạo lớp `Rectangle` có constructor nhận chiều rộng và chiều cao, phương thức `area()` trả diện tích; gọi qua `rectangle.area()`.

**Bài 2.** Tạo hai đối tượng `Counter` khác nhau, gọi `add` với các đối số khác nhau và giải thích vì sao trạng thái không tự đồng bộ.

**Bài 3.** Tạo `Counter alias = first` rồi gọi `alias.increment()`. Sau đó gán `alias = new Counter(...)` và dự đoán `first.current()`.

**Bài 4.** Viết phương thức trả `this` để hỗ trợ `counter.addAndReturn(2).addAndReturn(3)`. Thử thay kiểu trả về thành `void` rồi quan sát lỗi khi chaining.

**Bài 5.** Phân biệt lời gọi `object.instanceMethod()` và `ClassName.staticMethod()`. Nêu lý do gọi instance method qua null thất bại.

### Ghi nhớ

**`new Type(args)` tạo đối tượng và gọi constructor; biến kiểu lớp thường giữ tham chiếu tới đối tượng.** Dùng `object.method(args)` để gọi hành vi của **đối tượng nhận lời gọi**, kèm `(...)` cho phương thức. Hai biến có thể dùng chung đối tượng qua alias; hai lần `new` tạo đối tượng riêng. `static` thuộc lớp và nên gọi theo `Type.method(...)`; tham chiếu `null` không thể nhận lời gọi instance method.
