# Biến `var` giữ kiểu của lớp vô danh (Java 10+)

## 1. Mục tiêu bài học

Từ Java 10, Java hỗ trợ **suy luận kiểu cho biến cục bộ** (*local-variable type inference*) thông qua `var`. Một trường hợp đặc biệt và vẫn hữu ích đến các bản Java hiện đại là: **khi gán trực tiếp một biểu thức tạo lớp vô danh cho biến `var`, trình biên dịch giữ kiểu thực tế của lớp vô danh đó**, kể cả những thành viên mới khai báo bên trong phần thân lớp.

Nhờ vậy, mã có thể gọi một phương thức hoặc đọc một trường chỉ tồn tại trên lớp vô danh ngay tại nơi dùng biến cục bộ. Nếu cùng đối tượng được khai báo bằng kiểu cha như `Object` hoặc một interface, các thành viên riêng đó thường không truy cập được qua tham chiếu mang kiểu cha.

Sau bài này, bạn cần nắm:

- Lớp vô danh là gì, và vì sao không thể viết tên kiểu của nó trong mã nguồn Java thông thường.
- `var` giúp giữ **kiểu tĩnh của lớp vô danh** như thế nào.
- Vì sao cùng đối tượng có thể gọi được phương thức riêng qua `var` nhưng không gọi được qua `Object`/interface.
- Giới hạn khi trả đối tượng ra khỏi phương thức, gán cho kiểu cha, kết hợp nhiều lớp vô danh, hoặc dùng lambda.
- Khi nào nên dùng kỹ thuật này trong mã thực tế, và khi nào nên chọn một class, record hoặc interface có tên.

Đây là tính năng đã có từ **Java 10 (JEP 286)** và vẫn được ngôn ngữ Java hiện đại hỗ trợ; không cần dựa vào API đã lỗi thời hay cơ chế legacy để minh họa.

## 2. Lớp vô danh (*anonymous class*) là gì?

Một lớp vô danh là lớp được **khai báo và khởi tạo ngay trong một biểu thức** dạng `new SuperClass() { ... }` hoặc `new SomeInterface() { ... }`. Nó không có tên lớp được người viết mã đặt cho để sử dụng làm kiểu trong những khai báo khác.

Ví dụ:

```java
Object info = new Object() {
    String name = "Java";
    int version = 10;

    String label() {
        return name + " " + version;
    }
};
```

Đây là một đối tượng thực sự của một lớp vô danh **kế thừa `Object`**. Lớp vô danh khai báo thêm field `name`, `version` và phương thức `label()`. Tuy nhiên, biến `info` trong đoạn trên được khai báo có **kiểu tĩnh là `Object`**.

Do đó, dòng sau không biên dịch:

```java
// System.out.println(info.label()); // SAI: Object không khai báo label()
```

Dù object lúc chạy thật sự có `label()`, Java quyết định thành viên nào được phép gọi **từ kiểu tĩnh của biểu thức nhận lời gọi**. Kiểu `Object` không có phương thức `label()`. Trình biên dịch không tự nhìn xuyên qua kiểu `Object` để lộ các thành viên chỉ tồn tại trong một lớp con vô danh.

Mặt khác, các phương thức vốn có của `Object` như `toString()`, `hashCode()` và `getClass()` vẫn gọi được qua `info` vì chúng thuộc kiểu `Object`.

## 3. `var` giữ kiểu của lớp vô danh

Viết lại bằng `var`:

```java
var info = new Object() {
    String name = "Java";
    int version = 10;

    String label() {
        return name + " " + version;
    }
};

System.out.println(info.label());   // Java 10
System.out.println(info.version);   // 10
```

Đây là **các câu lệnh để đặt trong thân một phương thức hoặc khối khởi tạo**, không phải một tệp Java hoàn chỉnh. Chúng cho thấy sự khác biệt:

- Với `Object info = ...`, kiểu tĩnh của biến đã được **giới hạn về `Object`**; `label()` và `version` không nằm trong API nhìn thấy từ biến.
- Với `var info = ...`, compiler suy luận **kiểu lớp vô danh cụ thể** từ biểu thức khởi tạo. Kiểu này không có tên có thể viết trong mã nguồn, nhưng compiler vẫn biết đầy đủ các thành viên được khai báo trong nó.
- Sau khi suy luận, `info` là một biến **có kiểu tĩnh cố định**. Nó không chuyển kiểu theo cách dùng về sau.

Khái niệm chuyên môn của trường hợp này là **non-denotable type**: một kiểu compiler có thể mô tả, kiểm tra và sử dụng nhưng lập trình viên không thể viết một tên kiểu trực tiếp tương ứng ở vị trí khai báo. `var` giúp giữ kiểu không thể gọi tên đó trong một biến cục bộ.

Lưu ý: `var` **không tạo ra lớp vô danh**. Lớp được tạo từ cú pháp `new Object() { ... }`. `var` chỉ thay cách khai báo kiểu của **biến tham chiếu** tới instance ấy; object, phạm vi, quyền truy cập thành viên và các quy tắc Java thông thường vẫn giữ nguyên.

## 4. So sánh ba cách khai báo tham chiếu

Xét một lớp vô danh triển khai `Runnable` và khai báo thêm phương thức `description()`:

```java
var task = new Runnable() {
    @Override
    public void run() {
        System.out.println("running");
    }

    String description() {
        return "daily-report";
    }
};

task.run();                         // Hợp lệ: từ Runnable
System.out.println(task.description()); // Hợp lệ: thành viên riêng
```

Tuy nhiên:

```java
Runnable taskAsInterface = task;
taskAsInterface.run();              // Hợp lệ
// taskAsInterface.description();    // SAI khi biên dịch
```

Một cách so sánh:

| Cách khai báo | Kiểu tĩnh mà compiler dùng | Gọi `run()` | Gọi `description()` |
| --- | --- | --- | --- |
| `var task = new Runnable() { ... }` | Kiểu lớp vô danh cụ thể | Có | Có, vì kiểu suy luận chứa phương thức này |
| `Runnable task = new Runnable() { ... }` | `Runnable` | Có | Không, `Runnable` không khai báo phương thức ấy |
| `Object task = new Runnable() { ... }` | `Object` | Không gọi trực tiếp được `run()` | Không |

Cả ba cách đều có thể tham chiếu đến một **instance của lớp vô danh**, nhưng **hợp đồng kiểu tĩnh tại điểm gọi** khác nhau. `var` không vô hiệu hóa modifiers như `private`, `protected` hoặc quyền truy cập theo package; thành viên vẫn phải được truy cập hợp lệ theo quy tắc ngôn ngữ.

Đây là một ví dụ tốt về hai khái niệm cần tách biệt:

- **Kiểu runtime**: lớp thực sự của object được tạo ra.
- **Kiểu tĩnh**: kiểu dùng để compiler kiểm tra biểu thức và các lời gọi phương thức.

Khi gán một tham chiếu từ biến `var` sang `Object` hoặc `Runnable`, **object không đổi và không bị sao chép**; chỉ có kiểu tĩnh của biến nhận tham chiếu thay đổi.

## 5. Ví dụ hoàn chỉnh, chạy được từ Java 10

Tạo tệp **`AnonymousTypeDemo.java`**:

```java
public class AnonymousTypeDemo {
    private static Object passThrough(Object value) {
        return value;
    }

    public static void main(String[] args) {
        var ticket = new Object() {
            String product = "Notebook";
            int quantity = 2;
            int unitPrice = 75;

            int total() {
                return quantity * unitPrice;
            }

            String summary() {
                return product + " x" + quantity + " = " + total();
            }
        };

        System.out.println(ticket.summary());
        System.out.println("quantity=" + ticket.quantity);

        var alias = ticket;
        System.out.println("alias.total=" + alias.total());

        Object wide = ticket;
        System.out.println("runtime anonymous=" + wide.getClass().isAnonymousClass());

        var fromMethod = passThrough(ticket);
        System.out.println("returned as Object=" + fromMethod.getClass().isAnonymousClass());

        var job = new Runnable() {
            @Override
            public void run() {
                System.out.println("running job");
            }

            String details() {
                return "nightly";
            }
        };

        System.out.println(job.details());
        Runnable interfaceView = job;
        interfaceView.run();
    }
}
```

Biên dịch với cú pháp/ngữ nghĩa Java 10 và chạy:

```bash
javac --release 10 AnonymousTypeDemo.java
java AnonymousTypeDemo
```

Kết quả stdout **chính xác**:

```text
Notebook x2 = 150
quantity=2
alias.total=150
runtime anonymous=true
returned as Object=true
nightly
running job
```

Giải thích:

1. `ticket` được suy luận là kiểu lớp vô danh kế thừa `Object`, đồng thời khai báo `summary()`, `total()` và field `quantity`. Vì vậy cả `ticket.summary()` và `ticket.quantity` đều hợp lệ.
2. `var alias = ticket;` suy luận cùng kiểu tĩnh lớp vô danh với `ticket`. Do đó `alias.total()` vẫn hợp lệ; `alias` và `ticket` cùng tham chiếu một object, không có bản sao tự động.
3. `Object wide = ticket;` giữ nguyên object runtime. `wide.getClass().isAnonymousClass()` trả `true`, nhưng `wide.summary()` nếu gọi trực tiếp sẽ **không biên dịch**, vì kiểu tĩnh của `wide` là `Object`.
4. `passThrough` có kiểu trả về khai báo `Object`; do đó `var fromMethod = passThrough(ticket);` suy luận `Object`. Hàm trả về đúng object vô danh ban đầu, nhưng thông tin kiểu tĩnh về `summary()` đã không còn ở giá trị trả về.
5. `job` được suy luận là lớp vô danh **triển khai `Runnable`** và chứa thêm `details()`. `job.details()` hợp lệ, trong khi qua `Runnable interfaceView` chỉ còn các phương thức của giao diện tương ứng như `run()`.

Chương trình chạy không cần reflection để gọi thành viên riêng của lớp vô danh: compiler đã có thông tin kiểu phù hợp từ khai báo `var`. Lệnh `getClass().isAnonymousClass()` trong ví dụ chỉ dùng để xác minh bản chất runtime của object; nó không phải cơ chế cho phép `summary()` hoặc `details()` biên dịch.

## 6. Giữ và làm mất thông tin kiểu: xét theo từng biểu thức

### 6.1. Gán sang một biến `var` khác có thể giữ kiểu

```java
var original = new Object() {
    int answer() {
        return 42;
    }
};
var secondName = original;

System.out.println(secondName.answer()); // 42
```

Khi `secondName` được khai báo từ `original`, kiểu của initializer chính là kiểu tĩnh lớp vô danh đã suy luận cho `original`. Vì thế thành viên `answer()` vẫn nhìn thấy.

### 6.2. Khai báo kiểu cha hoặc ép kiểu làm thu hẹp API nhìn thấy

```java
Object asObject = original;
var inferredObject = (Object) original;

// asObject.answer();       // SAI: Object không khai báo answer()
// inferredObject.answer(); // SAI: vế khởi tạo bị ép kiểu Object
```

Điều quyết định là **kiểu tĩnh của biểu thức khởi tạo**. Chữ `var` không có khả năng tự truy tìm kiểu lớp cụ thể từ object runtime sau khi biểu thức đã được ép kiểu `Object`.

### 6.3. Phương thức có hợp đồng trả về kiểu cha

```java
static Object expose(Object value) {
    return value;
}

// Trong một phương thức khác:
// var result = expose(original); // result có kiểu Object.
// result.answer();               // SAI: Object không có answer().
```

Đây là đoạn minh họa chữ ký một phương thức và vài dòng gọi, không phải chương trình độc lập. Một khi API công bố kiểu trả về là `Object`, caller chỉ có thể sử dụng API của `Object` khi chưa có thao tác kiểm tra/ép kiểu khác thích hợp. Không thể đặt kiểu lớp vô danh làm kiểu trả về được viết trực tiếp trong chữ ký phương thức, vì lớp đó không có tên nguồn để khai báo.

Nếu các phương thức riêng cần được sử dụng ở **nhiều phương thức, nhiều file hoặc nhiều module**, hãy định nghĩa interface hoặc kiểu có tên rõ ràng.

## 7. Hai lớp vô danh có cùng thành viên vẫn là hai kiểu khác nhau

Xét:

```java
var first = new Object() {
    String label() {
        return "A";
    }
};
var second = new Object() {
    String label() {
        return "B";
    }
};

System.out.println(first.label());  // A
System.out.println(second.label()); // B
// first = second; // SAI: hai biểu thức new tạo hai kiểu lớp vô danh riêng
```

Hai lớp vô danh đều kế thừa `Object` và cùng có phương thức `label()`. Tuy nhiên, mỗi biểu thức `new Object() { ... }` khai báo một **lớp vô danh riêng**. Java có hệ kiểu danh nghĩa (*nominal typing*), không xem hai lớp tự động tương thích chỉ vì hình dạng các phương thức trùng nhau.

Vì vậy `first = second;` không phải một phép gán hợp lệ giữa hai kiểu vô danh khác nhau. Nếu muốn xử lý cả hai qua một hợp đồng chung, khai báo interface:

```java
interface Labelled {
    String label();
}

Labelled first = new Labelled() {
    @Override
    public String label() {
        return "A";
    }
};

Labelled second = new Labelled() {
    @Override
    public String label() {
        return "B";
    }
};

first = second; // Hợp lệ: cả hai cùng kiểu tĩnh Labelled
```

Đoạn này chỉ minh họa khai báo interface và các câu lệnh cần đặt trong một ngữ cảnh Java phù hợp; khi đặt vào cùng tệp, cần bố trí `Labelled` và các biến trong class/phương thức hợp lệ. Ý chính: **dùng một interface có tên để biểu đạt các thao tác chung**, còn `var` thuận tiện khi chỉ cần giữ một kiểu vô danh cục bộ.

## 8. Biểu thức điều kiện với hai lớp vô danh khác nhau

Trường hợp sau có vẻ mỗi nhánh đều khai báo `read()`, nhưng vẫn không cho phép gọi `read()` trên biến kết quả:

```java
boolean flag = true;

var combined = flag
        ? new Object() {
            int read() {
                return 1;
            }
        }
        : new Object() {
            int read() {
                return 2;
            }
        };

// combined.read(); // SAI: kiểu tĩnh chung không công bố read()
```

Ở ví dụ cụ thể này, toán tử điều kiện `?:` phải xác định **một kiểu chung** cho hai nhánh là hai lớp vô danh độc lập, cùng kế thừa `Object`. Kiểu suy luận cho `combined` là `Object`; do đó không có phương thức `read()` trong API nhìn thấy, dù object runtime ở nhánh được chọn có phương thức đó.

**Phương án tốt hơn khi cần cùng hành vi**:

```java
interface Reader {
    int read();
}

Reader combined = flag
        ? new Reader() {
            @Override
            public int read() {
                return 1;
            }
        }
        : new Reader() {
            @Override
            public int read() {
                return 2;
            }
        };

System.out.println(combined.read()); // 1 nếu flag == true
```

Hoặc để ngắn gọn hơn cho đúng một phương thức chức năng, có thể dùng `IntSupplier` có sẵn trong thư viện chuẩn:

```java
java.util.function.IntSupplier supplier =
        flag ? () -> 1 : () -> 2;

System.out.println(supplier.getAsInt()); // 1 nếu flag == true
```

Hai đoạn trên là **mã minh họa đặt trong ngữ cảnh Java có biến `flag` phù hợp**. Cách chọn phụ thuộc vào mục tiêu: cần một API có tên ổn định thì dùng interface; cần một hàm đơn giản và biểu diễn chức năng thì dùng functional interface/lambda.

## 9. `var` với lớp vô danh khác với `var` gán trực tiếp lambda

Lớp vô danh tạo ra một đối tượng có kiểu lớp cụ thể:

```java
var runnable = new Runnable() {
    @Override
    public void run() {
        System.out.println("Hello");
    }
};
runnable.run(); // Hợp lệ
```

Nhưng đoạn này **không hợp lệ**:

```java
// var runnable = () -> System.out.println("Hello");
// LỖI BIÊN DỊCH: lambda cần một target functional interface.
```

Một biểu thức lambda đứng độc lập không cung cấp kiểu đích đủ cho `var` suy luận. Khi cần lambda, hãy chỉ rõ functional interface:

```java
Runnable runnable = () -> System.out.println("Hello");
runnable.run();
```

Hoặc cung cấp kiểu đích bằng phép ép kiểu phù hợp:

```java
var runnable = (Runnable) () -> System.out.println("Hello");
runnable.run();
```

Ở ví dụ cuối, `runnable` được suy luận là kiểu `Runnable`, **không phải** một kiểu lớp vô danh có thêm các thành viên riêng. Trình biên dịch xử lý lambda theo hợp đồng functional interface.

Từ Java 11, cú pháp `var` còn có thể được dùng trong **khai báo tham số lambda** với những điều kiện riêng; đó là một khả năng khác, không làm biểu thức `var function = () -> ...` tự nhiên hợp lệ. Kiến thức chính của bài này bắt đầu từ Java 10 và vẫn áp dụng trên Java hiện đại.

## 10. Phạm vi truy cập, tính bất biến và vòng đời

Sự tiện lợi của `var` không thay đổi các luật thiết kế cơ bản.

**Phạm vi cục bộ.** `var` dùng cho biến cục bộ có initializer trong phương thức, constructor hoặc initializer block. Nó không hợp lệ làm kiểu khai báo của instance field, static field, tham số phương thức hoặc kiểu trả về. Do đó bạn có thể giữ kiểu vô danh trong một hàm, nhưng không dùng `var` để khai báo field công khai nhằm xuất bản kiểu ấy.

**Truy cập thành viên.** Có thể gọi thành viên khai báo trong lớp vô danh khi kiểu tĩnh thích hợp **và** quy tắc truy cập Java cho phép. `var` không làm một thành viên `private` của lớp khác tự trở thành public.

**Biến vẫn mutable nếu không có `final`.** Ví dụ:

```java
var counter = new Object() {
    int value = 0;

    void increment() {
        value++;
    }
};

counter.increment();
System.out.println(counter.value); // 1
```

`var` không làm field `value` bất biến, không thêm cơ chế thread-safety và không tạo snapshot. Nếu cần ngăn gán lại tham chiếu, có thể viết `final var counter = new Object() { ... };`; ngay cả khi đó, trạng thái mutable bên trong object vẫn có thể đổi.

**Capture biến ngoài.** Lớp vô danh có thể truy cập local variable ở phạm vi bao ngoài khi biến đó là `final` hoặc *effectively final*:

```java
String prefix = "ID-";

var formatter = new Object() {
    String format(int id) {
        return prefix + id;
    }
};

System.out.println(formatter.format(7)); // ID-7
// prefix = "NEW-"; // Nếu thêm phép gán này, prefix không còn effectively final.
```

Đó là quy tắc capture hiện hành của Java, không phải ngoại lệ do `var` mang lại.

**Tên class runtime.** Compiler/JVM có thể tạo tên nội bộ cho lớp vô danh, nhưng không nên phụ thuộc vào `getClass().getName()` hoặc tên dạng `Outer$1` làm một hợp đồng ổn định. Việc đổi vị trí các khai báo hoặc công cụ build có thể làm tên sinh ra thay đổi. Khi cần nhận dạng loại đối tượng trong API, hãy sử dụng một kiểu có tên hoặc metadata nghiệp vụ rõ ràng.

## 11. Khi nào nên dùng kỹ thuật này?

Kỹ thuật có giá trị khi một object chỉ phục vụ **một thuật toán ngắn, trong cùng một phạm vi**, và cấu trúc của nó được nhìn thấy ngay tại khai báo:

```java
var stats = new Object() {
    int success = 0;
    int failure = 0;

    int total() {
        return success + failure;
    }
};

stats.success++;
stats.failure++;
System.out.println(stats.total()); // 2
```

Đoạn này minh họa cách gói một số trạng thái cục bộ với hành vi đi kèm mà vẫn truy cập được thành viên của anonymous class nhờ `var`. Nó không có nghĩa đây là lựa chọn tốt nhất cho **mọi** nhóm dữ liệu tạm: nếu chỉ cần một hoặc hai biến, dùng biến cục bộ thông thường có thể rõ hơn.

Cần cân nhắc chọn một **class, record, interface hoặc một kiểu DTO có tên** khi:

- Đối tượng phải xuất hiện trong chữ ký API hoặc được trả về và sử dụng ở nhiều nơi.
- Nhiều implementation cần trao đổi cho nhau qua cùng một hợp đồng.
- Cấu trúc bắt đầu có nhiều field/phương thức, logic phức tạp hoặc cần kiểm thử độc lập.
- Cần serialization, mapping, reflection hoặc tương tác framework với metadata rõ ràng.
- Cần sự ổn định và dễ hiểu hơn là tận dụng một kiểu không thể gọi tên trong mã nguồn.

Trong Java 17+, `record` là lựa chọn phù hợp cho nhiều *data carrier* bất biến ở mức cấu trúc tham chiếu; tuy nhiên `record` cũng không tự tạo deep immutability cho mọi field chứa đối tượng mutable. Đó là một công cụ thiết kế API khác với lớp vô danh và không phải cú pháp sẵn có trong Java 10.

## 12. Các sai lầm dễ gặp

1. **Nghĩ `var` luôn suy luận kiểu cha**. Với initializer trực tiếp là `new Object() { ... }`, kiểu lớp vô danh được giữ, không tự hạ xuống `Object`.
2. **Nghĩ `var` đổi kiểu theo runtime**. Java vẫn kiểm tra kiểu tĩnh ở thời điểm biên dịch. Một biến khai báo từ expression có kiểu `Object` vẫn là `Object` dù nó trỏ tới object của lớp vô danh.
3. **Nghĩ hai anonymous class có cùng phương thức là cùng kiểu**. Mỗi biểu thức khai báo lớp vô danh mới tạo một kiểu riêng; không thể gán qua lại chỉ dựa vào cấu trúc thành viên giống nhau.
4. **Đánh đồng anonymous class với lambda**. Lớp vô danh có phần thân class và có thể chứa thêm thành viên; lambda là một biểu thức cần target functional interface, không thể gán trực tiếp cho `var` khi thiếu kiểu đích.
5. **Trả object qua phương thức kiểu `Object` rồi mong `var` khôi phục thành viên riêng**. `var result = methodReturningObject();` suy luận `Object` từ **kiểu trả về khai báo**, không từ class runtime.
6. **Dùng kiểu vô danh cho API dài hạn**. Kiểu không có tên phù hợp trong phạm vi cục bộ; một API cần công bố khả năng nên dùng interface/class có tên.
7. **Quên các quy tắc visibility và effectively final**. `var` không thay đổi quyền truy cập hoặc các quy tắc capture biến của anonymous class.
8. **Dựa vào tên class compiler sinh ra**. Tên như `$1` không phải cách định danh nghiệp vụ hoặc một hợp đồng API an toàn.

## 13. Tự kiểm tra

**Câu 1.** Vì sao đoạn này hợp lệ?

```java
var item = new Object() {
    String code() {
        return "A1";
    }
};
System.out.println(item.code());
```

**Đáp án:** `var` giữ kiểu tĩnh của lớp vô danh trực tiếp tạo bởi initializer; compiler biết phương thức `code()`.

**Câu 2.** Vì sao đoạn sau không biên dịch dù object có cùng nội dung?

```java
Object item = new Object() {
    String code() {
        return "A1";
    }
};
// item.code(); // lỗi
```

**Đáp án:** Biến có kiểu tĩnh `Object`, và `Object` không công bố `code()`.

**Câu 3.** Với `var next = item;` nếu `item` có kiểu tĩnh lớp vô danh, `next` có dùng được thành viên riêng của lớp đó không?

**Đáp án:** Có, nếu thành viên được truy cập hợp lệ, vì kiểu initializer `item` đã là kiểu lớp vô danh ấy.

**Câu 4.** Hai biểu thức `new Object() { int id() { return 1; } }` đặt ở hai vị trí có cùng kiểu không?

**Đáp án:** Không. Chúng tạo hai kiểu lớp vô danh riêng dù cùng tên và chữ ký phương thức.

**Câu 5.** `var consumer = (Runnable) () -> System.out.println("go");` có hợp lệ không, và kiểu suy luận là gì?

**Đáp án:** Hợp lệ vì phép ép kiểu cung cấp target functional interface cho lambda. Kiểu của biến là `Runnable`.

**Câu 6.** Muốn trả một đối tượng hỗ trợ `total()` qua API mà caller có thể gọi trực tiếp `total()`, nên công bố kiểu nào?

**Đáp án:** Định nghĩa một interface/class/record có tên với hợp đồng thích hợp, thay vì trả đối tượng lớp vô danh dưới kiểu `Object`.

## Tham khảo chính thức, vẫn có hiệu lực

- [OpenJDK — JEP 286: Local-Variable Type Inference](https://openjdk.org/jeps/286): đặc tả tính năng `var` từ Java 10, bao gồm trường hợp kiểu không thể gọi tên như anonymous class.
- [OpenJDK — Local Variable Type Inference FAQ](https://openjdk.org/projects/amber/guides/lvti-faq): `var` chỉ suy luận từ initializer, Java vẫn có kiểu tĩnh.
- [OpenJDK — Local Variable Type Inference Style Guidelines](https://openjdk.org/projects/amber/guides/lvti-style-guide): cách dùng `var` rõ ràng, tránh tạo kiểu khó hiểu.
- [Java Language Specification — ```14.4 Local Variables](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.4): khai báo biến cục bộ và quy tắc suy luận kiểu.
- [Java Language Specification — ```15.9.5 Anonymous Class Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.9.5): khai báo lớp vô danh và thành viên của nó.
