# Java 10 — Truy cập thành viên bổ sung của lớp vô danh qua biến cục bộ

## 1. Mục tiêu và bối cảnh

Trong Java, **lớp vô danh (anonymous class)** là một lớp được định nghĩa ngay tại biểu thức tạo đối tượng, không có tên kiểu để viết trực tiếp trong mã nguồn. Lớp đó có thể khai báo thêm field và method bên cạnh những thành viên kế thừa hoặc triển khai từ kiểu cha.

Từ **Java 10**, cơ chế **suy luận kiểu biến cục bộ** (`var`, JEP 286) giúp giữ lại kiểu cụ thể của một đối tượng lớp vô danh trong phạm vi biến cục bộ. Vì vậy, code có thể gọi **những thành viên bổ sung** của chính lớp vô danh thông qua biến `var`, ngay cả khi `Object` hoặc interface cha không khai báo các thành viên ấy.

Đây là quy tắc vẫn có hiệu lực trên các phiên bản Java hiện đại. Tuy nhiên, khả năng này phù hợp nhất với một phạm vi rất nhỏ; khi cần chia sẻ hành vi giữa các lớp hoặc xây dựng API công khai, nên khai báo kiểu có tên và hợp đồng rõ ràng.

Sau bài học, bạn có thể:

1. Phân biệt **kiểu tĩnh** suy ra từ `new Object() { ... }` với kiểu cha `Object`.
2. Truy cập field/method riêng do lớp vô danh khai báo qua biến cục bộ `var`.
3. Giải thích vì sao cùng một đối tượng nhưng tham chiếu kiểu `Object`/`Runnable` không gọi được method bổ sung.
4. Phân biệt trường hợp **khởi tạo trực tiếp bằng lớp vô danh** với trường hợp nhận object qua phương thức trả về kiểu cha.
5. Nhận ra các hạn chế: kiểu vô danh không có tên để dùng trong API, không thay thế tính đa hình theo interface, không thể gán một lớp vô danh khác chỉ vì các method giống nhau.
6. Lựa chọn lớp có tên hoặc interface khi đoạn code phát triển vượt phạm vi cục bộ.

## 2. Vì sao lớp vô danh có thể khai báo thành viên bổ sung?

Biểu thức như sau tạo ra một lớp con vô danh của `Object` và một instance của lớp ấy:

```java
new Object() {
    int amount = 0;

    void add(int value) {
        amount += value;
    }

    int total() {
        return amount;
    }
}
```

Đây là **biểu thức minh họa**, cần xuất hiện trong một ngữ cảnh sử dụng giá trị, chẳng hạn làm initializer. Những field `amount`, method `add` và `total` là thành viên **được khai báo ở lớp vô danh**; chúng **không** được thêm vào API của `java.lang.Object`.

Lớp vô danh đã có trong Java từ lâu, trước Java 10. Điều Java 10 đem lại ở đây là cú pháp khai báo biến cục bộ bằng `var` và quy tắc suy luận kiểu cho phép **giữ kiểu lớp vô danh ở compile time**, dù người lập trình không thể viết ra tên của kiểu đó trong source.

### 2.1. Trước và sau khi dùng `var`

Hai khai báo này tạo ra những đối tượng có cấu trúc tương tự, nhưng **biến có kiểu tĩnh khác nhau**:

```java
// Kiểu của conventional là Object.
Object conventional = new Object() {
    void greet() {
        System.out.println("Xin chào");
    }
};

// Kiểu của inferred là chính kiểu lớp vô danh tạo ra.
var inferred = new Object() {
    void greet() {
        System.out.println("Xin chào");
    }
};

inferred.greet();       // Hợp lệ từ Java 10
// conventional.greet(); // LỖI BIÊN DỊCH: Object không có greet()
```

Đây là **đoạn minh họa đặt trong một phương thức**, không phải file Java độc lập. Dòng gọi lỗi đã được chú thích để phần còn lại có thể biên dịch.

Với `Object conventional`, trình biên dịch chỉ cho phép gọi các thành viên có trên `Object` và thành viên truy cập được theo kiểu đó. Với `var inferred`, trình biên dịch suy ra **kiểu thực tế của biểu thức khởi tạo** là lớp vô danh, vì vậy nhìn thấy cả `greet()`.

**Điểm quan trọng:** `var` không phải kiểu động, không trì hoãn việc kiểm tra kiểu tới runtime và không thay đổi object. Cả hai trường hợp đều được Java kiểm tra kiểu tĩnh; sự khác biệt nằm ở **kiểu khai báo của biến**.

## 3. Quy tắc suy luận kiểu phía sau `var`

Theo quy tắc khai báo biến cục bộ trong Java Language Specification, khi viết:

```java
var name = initializer;
```

trình biên dịch xác định kiểu của `initializer` trong ngữ cảnh thích hợp rồi sử dụng kiểu suy ra cho biến cục bộ. Ở trường hợp:

```java
var helper = new Object() {
    String message() {
        return "Hello";
    }
};
```

kiểu của `new Object() { ... }` là **kiểu lớp vô danh riêng biệt** (anonymous class type), không đơn thuần là `Object`. `helper.message()` vì vậy được chấp nhận.

Kiểu của lớp vô danh là ví dụ về **kiểu không thể gọi tên trực tiếp trong mã nguồn (non-denotable type)**. Khả năng suy luận được kiểu này **không biến Java thành ngôn ngữ structural typing**: hai lớp vô danh cùng khai báo `message()` vẫn là hai kiểu khác nhau.

### 3.1. Ba thời điểm cần phân biệt

- **Khai báo biến:** Kiểu được suy ra **một lần** từ initializer; những phép gán phía sau không làm thay đổi kiểu đã suy ra.
- **Kiểm tra truy cập:** Một lời gọi `helper.message()` được kiểm tra dựa trên **kiểu tĩnh của biến `helper`**.
- **Khi chạy:** JVM giữ đối tượng thực sự thuộc lớp vô danh; việc biến tham chiếu được khai báo bằng `Object` không xóa method khỏi class, chỉ làm method đó không có trong **API nhìn thấy từ tham chiếu `Object`**.

Đây là lý do cùng một instance có thể được giữ trong hai biến nhưng chỉ một biến nhìn thấy thành viên bổ sung:

```java
var local = new Object() {
    int answer() {
        return 42;
    }
};
Object asObject = local;

System.out.println(local.answer());     // Hợp lệ
// System.out.println(asObject.answer()); // LỖI: Object không có answer()
```

Đoạn này có thể đặt trong `main`; khi chạy in ra `42`.

### 3.2. `var` trên một alias có giữ kiểu lớp vô danh không?

**Có**, nếu biểu thức gán cho alias vẫn có kiểu tĩnh là lớp vô danh:

```java
var first = new Object() {
    int score = 10;
    int getScore() {
        return score;
    }
};

var second = first;
System.out.println(second.getScore()); // 10
```

`second` nhận kiểu đã suy ra từ biểu thức `first`, nên vẫn gọi `getScore()` được. Ngược lại:

```java
Object third = first;
// third.getScore(); // Không hợp lệ vì third có kiểu Object
```

Sự khác biệt dựa trên **kiểu tĩnh của biểu thức initializer**, không dựa trên tên biến hay object identity.

## 4. Chương trình chạy được: truy cập field và method bổ sung

Lưu mã nguồn vào file **`AnonymousMembersDemo.java`**.

```java
public class AnonymousMembersDemo {

    public static void main(String[] args) {
        // Kiểu tĩnh được suy ra là chính lớp vô danh.
        var progress = new Object() {
            String topic = "Java 10";
            int completed;

            void add(int amount) {
                completed += amount;
            }

            String summary() {
                return topic + ": " + completed;
            }
        };

        // Object không có add(), summary() hay completed.
        // Nhưng biến progress có kiểu lớp vô danh nên gọi được.
        progress.add(2);
        progress.add(3);

        System.out.println(progress.summary());
        System.out.println("completed=" + progress.completed);

        // var cũng giữ kiểu này khi khởi tạo từ biến đã có kiểu đó.
        var sameType = progress;
        sameType.add(1);
        System.out.println("fromAlias=" + sameType.summary());

        // Ví dụ tương tự với lớp vô danh triển khai Runnable.
        var task = new Runnable() {
            int runs;

            @Override
            public void run() {
                runs++;
            }

            int timesRun() {
                return runs;
            }
        };

        task.run();
        task.run();
        System.out.println("anonymousTask=" + task.timesRun());

        // Upcast qua interface: vẫn cùng đối tượng,
        // nhưng API trên biến narrowed chỉ có những gì Runnable cho phép.
        Runnable narrowed = task;
        narrowed.run();
        System.out.println("afterInterface=" + task.timesRun());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 AnonymousMembersDemo.java
java AnonymousMembersDemo
```

**Stdout chính xác:**

```text
Java 10: 5
completed=5
fromAlias=Java 10: 6
anonymousTask=2
afterInterface=3
```

Giải thích:

1. `progress` được khai báo bằng `var` với initializer là `new Object() { ... }`. Vì kiểu suy ra là lớp vô danh, các thành viên `add`, `summary` và `completed` đều truy cập được.
2. Sau `add(2)` và `add(3)`, tổng bằng 5. `sameType` tham chiếu tới **cùng object**, nên `sameType.add(1)` làm tổng tăng thành 6.
3. `task` được suy ra là lớp vô danh **triển khai `Runnable`**, không chỉ là `Runnable`. Vì vậy có thể gọi cả `run()` (từ contract) và `timesRun()` (method bổ sung).
4. `narrowed` giữ cùng instance với `task` nhưng được khai báo `Runnable`. `narrowed.run()` vẫn chạy và làm tăng biến đếm trong object; sau đó `task.timesRun()` báo 3.
5. Nếu bỏ chú thích và viết `narrowed.timesRun()`, trình biên dịch sẽ báo lỗi vì **interface `Runnable` không khai báo phương thức đó**.

Chương trình này chỉ dùng ngôn ngữ/API đã tồn tại ở Java 10, dù chọn `--release 17` làm mức Java hiện đại để thực hành. Nếu có JDK hỗ trợ `--release 10`, cùng mã nguồn này cũng có thể biên dịch với:

```bash
javac --release 10 AnonymousMembersDemo.java
java AnonymousMembersDemo
```

Ở ví dụ trên, không cần reflection, thư viện ngoài hoặc cờ preview.

## 5. Những trường hợp thành viên bổ sung “biến mất” khỏi API nhìn thấy

### 5.1. Khai báo ngay từ đầu bằng kiểu cha

```java
Object info = new Object() {
    String label() {
        return "local";
    }
};

// info.label(); // LỖI BIÊN DỊCH
System.out.println(info.getClass() != Object.class); // true
```

Kết quả đối tượng runtime có lớp riêng **không** làm khai báo tĩnh `Object info` biến thành lớp vô danh. `Object` không có `label()`. `getClass()` cho thấy kiểu runtime khác `Object`, nhưng việc sử dụng `getClass()` không mở quyền gọi thành viên mới qua kiểu `Object`.

### 5.2. Cast sang kiểu cha trước khi suy luận

```java
var info = (Object) new Object() {
    String label() {
        return "local";
    }
};

// info.label(); // LỖI BIÊN DỊCH
```

Ở đây initializer là **biểu thức cast có kiểu `Object`**, nên `var` suy ra `Object`. Tên `var` không tự “nhìn xuyên qua” phép cast để lấy lại kiểu lớp vô danh.

### 5.3. Nhận instance qua phương thức trả về kiểu cha

```java
static Object create() {
    return new Object() {
        String label() {
            return "local";
        }
    };
}

// Bên trong phương thức sử dụng:
var info = create();
// info.label(); // LỖI: kiểu tĩnh của create() là Object
```

Đây là các **mảnh mã đặt trong một class phù hợp**, không phải chương trình độc lập. `create()` trả `Object`, cho nên `var info` suy ra `Object` bất kể lớp runtime được tạo bên trong phương thức là gì.

Tương tự, nếu một phương thức khai báo kiểu trả về `Runnable` hoặc một interface riêng, phía gọi chỉ nhìn thấy API của kiểu trả về ấy. Khi cần gọi `label()` từ bên ngoài, hãy đưa phương thức vào một interface/class **có tên** thay vì dựa vào chi tiết của lớp vô danh.

### 5.4. Hai lớp vô danh có hình dạng giống nhau vẫn khác kiểu

Ví dụ **cố ý không biên dịch**:

```java
var first = new Object() {
    void reset() {}
};

first = new Object() {
    void reset() {}
}; // LỖI: lớp vô danh thứ hai là một kiểu khác
```

Mỗi biểu thức tạo lớp vô danh khai báo một lớp riêng biệt. Tên `reset` trùng nhau không có nghĩa các lớp tương thích để gán. Suy luận kiểu của `var` **vẫn là kiểm tra kiểu danh nghĩa (nominal typing)**, không phải so sánh cấu trúc danh sách method.

Đây cũng là lý do không nên dùng anonymous class như một cách tạo “kiểu object tùy ý” cho các tầng khác nhau của chương trình. Nếu nhiều nơi cần cùng một hợp đồng, định nghĩa một interface/class có tên sẽ ổn định và dễ bảo trì hơn.

## 6. Vì sao tính năng này chỉ nên dùng trong phạm vi cục bộ?

### 6.1. Giới hạn của `var`

`var` của Java 10 được dùng trong các ngữ cảnh khai báo biến cục bộ phù hợp (biến trong block, vòng lặp, tài nguyên `try-with-resources`). Không được viết như kiểu của:

- Field: `var progress = ...;` trực tiếp như field của class là sai.
- Tham số phương thức thông thường: `void run(var input)` là sai.
- Kiểu trả về phương thức: `var create() { ... }` là sai.

Để một phương thức trả về một object và cho người gọi truy cập method, kiểu trả về phải là một **kiểu hợp lệ có tên hoặc một kiểu có thể biểu diễn trong khai báo**, thường là class/interface. Bạn không thể viết chính xác tên lớp vô danh trong khai báo trả về vì lớp đó không có tên Java nguồn.

### 6.2. Những lý do nên giữ ví dụ nhỏ

- **Dễ đọc:** Người xem phải đọc toàn bộ initializer để biết `var progress` có các method nào.
- **Dễ đổi cấu trúc:** Khi di chuyển code sang một factory trả kiểu cha, những lời gọi method bổ sung sẽ không còn biên dịch.
- **Không phải API:** Không thể mô tả contract công khai dựa trên một kiểu vô danh không có tên.
- **Khó tái sử dụng:** Hai lần tạo lớp vô danh có hình dạng giống nhau vẫn là hai kiểu riêng.
- **Không thay thế encapsulation:** Các trường dữ liệu hoặc method mới vẫn phải tuân thủ các quy tắc truy cập của Java; `var` không vượt qua `private`, package hoặc các ràng buộc kiểu.
- **Không phải immutable:** `var` chỉ suy luận kiểu; field trong ví dụ có thể thay đổi. Nếu muốn tham chiếu không thể gán lại, dùng `final var`, nhưng điều đó cũng không làm object trở thành bất biến.

### 6.3. Khi nào có thể dùng hợp lý?

Một trường hợp sử dụng hợp lý là **helper được tạo một lần, có số ít hành vi, chỉ tồn tại trong một phương thức ngắn**, ví dụ một bộ đếm phục vụ thử nghiệm hoặc xử lý cục bộ. Khi method phụ tăng nhiều, cần chia sẻ cho phương thức khác hoặc cần kiểm thử độc lập, bạn nên cân nhắc tạo kiểu có tên.

Hãy phân biệt hai mục tiêu:

- **Muốn thao tác cục bộ với vài field/method:** `var` + anonymous class có thể gọn và đúng.
- **Muốn mô hình có contract, được gọi ở nhiều nơi:** một class/interface có tên là lựa chọn dễ bảo trì.

## 7. Thiết kế thay thế khi hành vi cần được sử dụng lâu dài

### 7.1. Local class có tên

Nếu một đoạn xử lý cục bộ đã có nhiều trạng thái và phương thức, local class giúp nêu rõ một kiểu có tên mà vẫn giới hạn phạm vi sử dụng trong method.

Tệp độc lập **`LocalClassAlternative.java`**:

```java
public class LocalClassAlternative {
    public static void main(String[] args) {
        class Counter {
            private int value;

            void add(int delta) {
                value += delta;
            }

            int total() {
                return value;
            }
        }

        var counter = new Counter();
        counter.add(4);
        counter.add(2);

        System.out.println("total=" + counter.total());
    }
}
```

```bash
javac --release 17 LocalClassAlternative.java
java LocalClassAlternative
```

```text
total=6
```

Ở đây `var` suy ra **`Counter`**, một local class có tên, thay vì một lớp vô danh. Nó vẫn là khai báo biến cục bộ kiểu tĩnh và không yêu cầu đưa lớp này thành API công khai.

### 7.2. Interface có tên khi cần contract rõ ràng

Ví dụ **mảnh thiết kế**, đặt các khai báo sau trong phạm vi Java hợp lệ:

```java
interface CounterService {
    void add(int amount);
    int total();
}

CounterService counter = new CounterService() {
    private int current;

    @Override
    public void add(int amount) {
        current += amount;
    }

    @Override
    public int total() {
        return current;
    }
};

counter.add(5);
System.out.println(counter.total()); // 5
```

Phần khai báo `CounterService` phải nằm trong class hoặc ở cấp package; phần tạo `counter` đặt trong method/initializer phù hợp. Không cần dựa vào việc người gọi suy ra lớp vô danh: họ chỉ cần biết interface `CounterService`. Khi muốn thay implementation trong tương lai, code phụ thuộc vào interface tiếp tục sử dụng được.

### 7.3. Khi chỉ cần một hành vi, cân nhắc lambda

Nếu bài toán chỉ có **một hành vi** không cần khai báo thêm state/method ngoài hợp đồng, functional interface + lambda thường ngắn gọn hơn anonymous class:

```java
java.util.function.IntUnaryOperator twice = n -> n * 2;
System.out.println(twice.applyAsInt(4)); // 8
```

Lambda có **kiểu đích functional interface**. Đừng nhầm quy tắc này với khả năng của `var`: viết `var twice = n -> n * 2;` vẫn **sai** vì lambda đứng riêng không có target type. Một anonymous class với thành viên bổ sung và một lambda được dùng qua interface là hai công cụ khác nhau, không nên hoán đổi chỉ để theo đuổi cú pháp ngắn.

## 8. Các lỗi và hiểu lầm thường gặp

| Hiểu nhầm | Điều đúng |
|---|---|
| “`var` là kiểu động nên gọi được method runtime nào cũng được.” | `var` suy luận **kiểu tĩnh** tại compile time; chỉ gọi được các thành viên truy cập được theo kiểu đã suy ra. |
| “`Object x = new Object() { ... };` cũng gọi được method bổ sung.” | `x` có kiểu `Object`; method bổ sung không nằm trong API của `Object`. |
| “Bản thân Java 10 mới thêm anonymous class.” | Anonymous class có từ lâu; Java 10 thêm **suy luận kiểu biến cục bộ** cho phép giữ kiểu vô danh. |
| “`var x = (Object) new Object() { ... };` vẫn giữ kiểu vô danh.” | Cast khiến initializer có kiểu `Object`, nên `var` suy ra `Object`. |
| “Nếu object runtime có method, biến trả từ factory chắc chắn gọi được method ấy.” | Phải xét **kiểu trả về khai báo của factory**. |
| “Hai lớp vô danh cùng có `reset()` có thể gán cho nhau.” | Không. Mỗi biểu thức lớp vô danh tạo kiểu riêng; Java vẫn kiểm tra kiểu danh nghĩa. |
| “`final var` khiến toàn bộ object không đổi.” | `final` chỉ ngăn gán lại tham chiếu, không tự làm field/object bất biến. |
| “Dùng anonymous class + `var` luôn tốt hơn class có tên.” | Chỉ hợp lý khi phạm vi nhỏ, ít logic; code cần hợp đồng lâu dài nên có kiểu tên rõ ràng. |
| “Đã có `var` thì `var f = x -> x + 1;` cũng hợp lệ.” | Lambda là poly expression cần target functional interface, không thể suy ra từ initializer đứng riêng như đối tượng anonymous class. |

### 8.1. Tránh nhầm “không truy cập được” với “không tồn tại”

Đối tượng được tạo bằng `new Object() { void special() {} }` thực sự có `special()` ở lớp runtime. Khi tham chiếu có kiểu `Object`, trình biên dịch **không cho viết lời gọi `special()` qua tham chiếu đó**. Không nên dùng reflection để lách ranh giới kiểu chỉ nhằm gọi một method bạn đang chủ động thiết kế; hãy khai báo interface/class có hợp đồng rõ ràng.

### 8.2. Tránh làm lộ chi tiết implementation

Ví dụ `var progress = new Object() { ... }` khiến code bên dưới phụ thuộc vào các field/method riêng của lớp vô danh. Nếu refactor initializer sang `makeProgress()` với kiểu trả về `Object`, các lời gọi bổ sung sẽ lỗi biên dịch. Có thể đây chính là dấu hiệu rằng chương trình nên có kiểu `Progress` hoặc `ProgressView` có tên.

### 8.3. Không thêm cast tùy tiện

Phép cast sang `Object` hoặc interface cha **không** giúp truy cập thêm method; nó thường làm mất thông tin kiểu tĩnh mà `var` vừa giữ. Muốn tăng tính rõ ràng, hãy chọn kiểu khai báo mô tả contract thay vì cast để che lỗi.

## 9. Kiểm chứng quy tắc bằng trình biên dịch

Trên JDK 17+, bạn có thể lưu chương trình chạy được trong mục 4 và 7 rồi chạy:

```bash
javac --release 17 AnonymousMembersDemo.java
java AnonymousMembersDemo

javac --release 17 LocalClassAlternative.java
java LocalClassAlternative
```

Muốn tự quan sát lỗi biên dịch, tạo file **`NoExtraMemberOnObject.java`** với chủ đích **không biên dịch được**:

```java
public class NoExtraMemberOnObject {
    public static void main(String[] args) {
        Object item = new Object() {
            void extra() {
                System.out.println("extra");
            }
        };

        item.extra(); // Không tồn tại trong Object
    }
}
```

```bash
javac --release 17 NoExtraMemberOnObject.java
```

Trình biên dịch báo lỗi với ý nghĩa `cannot find symbol: method extra()` trên biến `item`. Thông điệp chi tiết, dòng và vị trí caret tùy JDK, nhưng **lý do là kiểu tĩnh `Object` không khai báo `extra()`**. Khi sửa `Object item` thành `var item` trong cùng đoạn mã, lời gọi sẽ được chấp nhận.

Để xác định **mức Java tối thiểu**, bản thân tính năng `var` của bài yêu cầu Java 10. Khi dự án dùng JDK mới để build mã hướng tới Java 10, hãy dùng `javac --release 10` (nếu JDK đó hỗ trợ target release 10); không được phụ thuộc vào syntax/API chỉ có từ các bản sau. Khi sửa code theo phiên bản dự án, cần xét cả thư viện phụ thuộc và môi trường runtime; `--release` chủ yếu kiểm tra mức ngôn ngữ/API của nền tảng Java.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Đoạn nào gọi được `value()`?

```java
var a = new Object() { int value() { return 1; } };
Object b = new Object() { int value() { return 2; } };
```

**Đáp án:** `a.value()` hợp lệ; `b.value()` không hợp lệ. `a` có kiểu lớp vô danh, còn `b` có kiểu `Object`.

**Câu 2.** Sau `Object b = a;`, `b.value()` có chạy không?

**Đáp án:** Không biên dịch vì kiểu tĩnh của `b` là `Object`. Bản thân object được tham chiếu không đổi.

**Câu 3.** `var c = a;` có còn gọi được `c.value()` không?

**Đáp án:** Có. Kiểu initializer `a` là kiểu lớp vô danh nên `c` nhận cùng kiểu tĩnh ấy.

**Câu 4.** Hai biểu thức `new Object() { int value() { return 1; } }` khác nhau có cùng kiểu không?

**Đáp án:** Không. Dù có cùng thành viên, mỗi khai báo lớp vô danh tạo ra một kiểu riêng.

**Câu 5.** Nếu `create()` khai báo trả `Object` nhưng trả về một instance lớp vô danh, `var x = create(); x.value();` có chạy không?

**Đáp án:** Không. Kiểu của lời gọi `create()` là `Object`, nên `var` suy ra `Object`.

**Câu 6.** Khi nào nên thay anonymous class bằng một kiểu có tên?

**Đáp án:** Khi method bổ sung là phần hợp đồng cho code khác, khi muốn tái sử dụng hoặc test độc lập, hoặc khi logic phát triển đủ lớn khiến việc phải đọc initializer mới hiểu được `var` trở nên khó bảo trì.

## 11. Tài liệu chính thức

- [OpenJDK JEP 286 — Local-Variable Type Inference](https://openjdk.org/jeps/286): tính năng Java 10, suy luận kiểu biến cục bộ và các kiểu không thể gọi tên.
- [Java Language Specification, Java 21 — Local Variable Declarations (`14.4)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.4): cách xác định kiểu từ initializer.
- [Java Language Specification, Java 21 — Class Instance Creation Expressions (`15.9)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.9): quy tắc biểu thức tạo instance và lớp vô danh.
- [Oracle Java 17 — Local Variable Type Inference](https://docs.oracle.com/en/java/javase/17/language/local-variable-type-inference.html): áp dụng `var` trong các phiên bản Java hiện đại.
- [OpenJDK — FAQ về Local Variable Type Inference](https://github.com/openjdk/amber-docs/blob/master/site/guides/lvti-faq.md): quy tắc suy luận tĩnh và hướng dẫn sử dụng `var` dễ bảo trì.

**Ghi nhớ:** `var a = new Object() { void extra() {} };` giữ kiểu cụ thể của lớp vô danh, nên có thể gọi `a.extra()` trong phạm vi biến cục bộ. `Object a = ...` hoặc `var a = (Object) ...` chỉ cho phép truy cập API của `Object`. Sự khác nhau là **kiểu tĩnh** — không phải quyền truy cập runtime đặc biệt hay kiểu động.