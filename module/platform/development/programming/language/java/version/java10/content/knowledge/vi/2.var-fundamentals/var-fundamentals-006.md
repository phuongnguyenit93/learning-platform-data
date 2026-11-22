# Kiểu của biến sau khi được gán lại: `var` trong Java 10+

## 1. Mục tiêu và kết luận cốt lõi

Trong Java, khi bạn viết `var` để khai báo một biến cục bộ, trình biên dịch **suy luận kiểu đúng một lần, từ biểu thức khởi tạo**. Những phép gán tiếp theo có thể thay đổi **giá trị hoặc đối tượng mà biến tham chiếu đến**, nhưng **không làm thay đổi kiểu tĩnh của biến**.

Ví dụ:

```java
var number = 10; // Kiểu tĩnh được suy luận là int
number = 20;     // Hợp lệ: kiểu vẫn là int
// number = "20"; // Lỗi biên dịch: String không thể gán cho int
```

Về kiểm tra kiểu, ví dụ trên tương đương:

```java
int number = 10;
number = 20;
```

**Điều cần ghi nhớ:** Java vẫn là ngôn ngữ **kiểu tĩnh (statically typed)** khi dùng `var`. `var` không phải biến kiểu động, không khiến trình biên dịch suy luận lại kiểu sau mỗi lần gán. Quy tắc này có hiệu lực từ Java 10 đến các phiên bản Java hiện đại.

Sau bài học, bạn sẽ biết cách dự đoán kiểu của biến sau khi gán lại, xác định phép gán nào hợp lệ, phân biệt kiểu tĩnh với kiểu đối tượng ở thời gian chạy, và lựa chọn khai báo phù hợp khi dự kiến đổi giá trị hoặc implementation.

## 2. Phân biệt khai báo, suy luận kiểu và gán lại

Xem ba thời điểm:

```java
var message = "start"; // (1) Khai báo + khởi tạo: suy luận String
message = "running";   // (2) Gán lại: kiểm tra giá trị mới tương thích với String
message = null;        // (3) Gán lại: null hợp lệ với kiểu tham chiếu String
```

| Thời điểm | Điều trình biên dịch làm | Điều không xảy ra |
| --- | --- | --- |
| `var message = "start";` | Dùng kiểu của biểu thức khởi tạo, suy luận `String`. | Không tạo một biến “chưa xác định kiểu”. |
| `message = "running";` | Kiểm tra phép gán mới có tương thích với `String` không. | Không chạy lại cơ chế suy luận kiểu của `var`. |
| `message = null;` | Cho phép `null` vì `String` là kiểu tham chiếu. | Không đổi kiểu biến thành “kiểu null”. |

Có thể xem phép khai báo `var name = initializer;` như một phép tính kiểu tại **thời điểm biên dịch**. Sau đó, phần lớn quy tắc áp dụng cho biến giống hệt khi bạn viết `String name`, `int name`, `List<String> name` hoặc kiểu tường minh tương ứng.

**Lưu ý về thuật ngữ:**

- **Kiểu tĩnh / kiểu khai báo:** kiểu mà trình biên dịch dùng để kiểm tra các phép gán và lời gọi phương thức.
- **Giá trị hiện tại:** dữ liệu mà biến đang chứa; có thể thay đổi sau phép gán.
- **Kiểu runtime của đối tượng:** với biến tham chiếu, đây là lớp thực sự của đối tượng đang được trỏ đến. Lớp này có thể khác nhau giữa các lần gán nhưng phải phù hợp với kiểu tĩnh của biến.

## 3. Phép gán lại hợp lệ dựa vào kiểu ban đầu

Trong câu lệnh `variable = expression;`, trình biên dịch kiểm tra xem giá trị của `expression` có thể được **chuyển đổi theo ngữ cảnh gán (assignment context)** sang kiểu đã cố định của `variable` hay không. Không bắt buộc hai vế có kiểu được viết giống nhau tuyệt đối: Java hỗ trợ một số chuyển đổi như **mở rộng kiểu số**, **mở rộng kiểu tham chiếu**, **boxing/unboxing**.

### 3.1. Gán đúng cùng kiểu

```java
var count = 1;          // int
count = 2;              // Hợp lệ: int -> int

var label = "pending";  // String
label = "done";         // Hợp lệ: String -> String
```

Nếu giá trị mới không thể chuyển đổi sang kiểu tĩnh, phép gán không biên dịch:

```java
var count = 1;          // int
// count = 2.5;         // Lỗi: double không thể gán ngầm cho int
// count = "two";       // Lỗi: String không thể gán cho int
```

### 3.2. Gán có mở rộng kiểu nguyên thủy (widening primitive conversion)

```java
var total = 10L;     // long
total = 20;          // Hợp lệ: int được mở rộng thành long; total vẫn là long

var ratio = 1.5;     // double
ratio = 3;           // Hợp lệ: int được mở rộng thành double; ratio vẫn là double
```

Giá trị `20` ban đầu là biểu thức `int`, nhưng được chuyển sang `long` **để gán** vào `total`. Đây là chuyển đổi của **giá trị**, không phải đổi kiểu của **biến**.

Chiều ngược lại không tự động hợp lệ:

```java
var total = 10;      // int
// total = 20L;      // Lỗi: long -> int là thu hẹp kiểu
// total = 2.5;      // Lỗi: double -> int là thu hẹp kiểu

total = (int) 2.5;   // Hợp lệ nhờ ép kiểu tường minh; total vẫn là int, giá trị 2
```

Đừng thay một khai báo `long total = 10;` bằng `var total = 10;` một cách máy móc: literal `10` khiến kiểu biến chuyển từ `long` sang `int`. Nếu muốn `long` mà vẫn dùng `var`, hãy viết `var total = 10L;`.

### 3.3. Boxing và unboxing không thay đổi kiểu của biến

```java
var primitive = 1;                  // int
primitive = Integer.valueOf(2);     // Hợp lệ: Integer được unbox thành int
// primitive = null;                // Lỗi: null không gán được cho int

var wrapper = Integer.valueOf(1);  // Integer
wrapper = 2;                       // Hợp lệ: int được box thành Integer
wrapper = null;                    // Hợp lệ: Integer là kiểu tham chiếu
```

Khi `wrapper` được gán `2`, biến vẫn có kiểu `Integer`. Khi `primitive` nhận một `Integer`, biến vẫn có kiểu `int`.

**Cẩn thận:** Nếu biểu thức `Integer` có giá trị `null` mà bạn gán cho `int`, bước unboxing có thể ném `NullPointerException` tại thời gian chạy. `var` không tự loại bỏ rủi ro này.

### 3.4. Một ngoại lệ cần biết: hằng số nguyên vừa với `byte`, `short` hoặc `char`

Không nên khái quát rằng “mọi phép thu hẹp kiểu trong phép gán đều bị cấm”. Java cho phép một số **biểu thức hằng số** kiểu nguyên được thu hẹp ngầm nếu giá trị nằm trong miền của kiểu đích.

```java
var small = (byte) 1; // Kiểu được suy luận là byte
small = 2;            // Hợp lệ: hằng số int 2 nằm trong phạm vi byte
// small = 200;        // Lỗi: 200 không biểu diễn được bằng byte

int next = 3;
// small = next;       // Lỗi: next là biến int, không phải biểu thức hằng số phù hợp
```

Dù `small = 2` hợp lệ, kiểu của `small` vẫn là `byte`. Quy tắc này thuộc **assignment conversion**, không phải cơ chế suy luận kiểu mới.

## 4. Kiểu tham chiếu: đối tượng có thể đổi, kiểu biến vẫn cố định

Một biến tham chiếu giữ tham chiếu tới đối tượng. Khi gán lại, đối tượng được trỏ tới có thể thay đổi. **Kiểu tĩnh của biến vẫn giữ nguyên**.

### 4.1. Gán một đối tượng khác có cùng kiểu

```java
var builder = new StringBuilder("A"); // Kiểu tĩnh: StringBuilder
builder = new StringBuilder("B");     // Hợp lệ; vẫn StringBuilder
// builder = new StringBuffer("C");   // Lỗi: StringBuffer không phải StringBuilder
```

Hai đối tượng `StringBuilder` có thể khác nhau, nhưng điều đó không có nghĩa kiểu biến thay đổi.

### 4.2. Kiểu con có thể gán cho biến kiểu cha/interface

Với interface `Pet` và hai lớp `Dog`, `Cat` đều triển khai `Pet`:

```java
Pet pet = new Dog(); // Kiểu tĩnh: Pet
pet = new Cat();     // Hợp lệ: Cat triển khai Pet
```

Sau lệnh gán, **kiểu tĩnh vẫn là `Pet`**, còn đối tượng hiện tại có lớp runtime `Cat`. Khi gọi phương thức được định nghĩa bởi `Pet`, Java thực thi implementation tương ứng với đối tượng hiện tại (đa hình).

Nếu viết `var pet = new Dog();`, kiểu suy luận là `Dog`, nên `pet = new Cat();` **không hợp lệ** khi `Dog` và `Cat` là hai lớp ngang hàng. `var` không tự chọn kiểu chung `Pet` chỉ vì những câu gán phía sau có thể muốn dùng lớp khác.

Về mặt cú pháp, có thể ép kiểu initializer để `var` suy luận interface:

```java
var pet = (Pet) new Dog(); // Kiểu tĩnh được suy luận là Pet
pet = new Cat();           // Hợp lệ
```

Tuy nhiên, khi **interface là ý định thiết kế**, viết `Pet pet = new Dog();` thường rõ nghĩa hơn và tránh một ép kiểu chỉ để điều khiển suy luận.

### 4.3. Mở rộng kiểu tham chiếu không làm biến “thành kiểu con”

```java
Object value = "Java";  // Kiểu tĩnh: Object
value = Integer.valueOf(7); // Hợp lệ: Integer là Object
```

Lúc đầu `value` trỏ tới `String`, sau đó tới `Integer`. Trình biên dịch vẫn nhìn `value` là `Object`; bạn không thể mặc nhiên gọi các phương thức chỉ có trên `String` hoặc `Integer`. Việc cần xử lý hành vi theo kiểu runtime có thể dùng `instanceof` và pattern matching khi phù hợp.

Lưu ý: `var value = new Object();` cũng suy luận `Object`, nên có thể nhận các đối tượng `String` và `Integer` về sau. Đó là do **kiểu ban đầu đã rộng**, chứ không phải do `var` biến thành kiểu động.

## 5. Thay implementation: generic và interface tác động thế nào?

Đây là nơi hiểu sai về “kiểu sau khi gán lại” gây lỗi phổ biến.

```java
var names = new java.util.ArrayList<String>(); // ArrayList<String>
names = new java.util.ArrayList<String>();      // Hợp lệ
// names = new java.util.LinkedList<String>();  // Lỗi: LinkedList<String> không là ArrayList<String>
```

Cả `ArrayList<String>` và `LinkedList<String>` đều triển khai `List<String>`, nhưng **`names` đã được suy luận là lớp cụ thể `ArrayList<String>`**. Không có chuyện gán `LinkedList<String>` rồi trình biên dịch mở rộng kiểu của `names` thành `List<String>`.

Khi cần thay implementation, khai báo interface:

```java
java.util.List<String> names = new java.util.ArrayList<>();
names = new java.util.LinkedList<>(); // Hợp lệ: cả hai là List<String>
```

Trường hợp khác đáng chú ý:

```java
var items = java.util.List.of("An");        // Kiểu tĩnh: List<String>
items = new java.util.ArrayList<String>(); // Hợp lệ: vẫn List<String>
items.add("Binh");                          // Hợp lệ với ArrayList hiện tại
```

`List.of(...)` tạo một danh sách **không cho phép sửa phần tử**; nó không làm cho **biến** trở thành `final`. Khi `items` được gán một `ArrayList` mới, lời gọi `add` hoạt động trên đối tượng mới. Phân biệt:

- **Gán lại biến (reassignment):** đổi tham chiếu đang giữ, ví dụ `items = ...`.
- **Thay đổi trạng thái đối tượng (mutation):** gọi `items.add(...)` hoặc một phương thức chỉnh sửa nội dung.
- **Kiểu tĩnh:** `List<String>` trong cả hai lần gán ở ví dụ trên.
- **Khả năng sửa đối tượng:** phụ thuộc vào implementation hiện tại, không chỉ vào `var`.

### Bẫy diamond operator `<>`

```java
var values = new java.util.ArrayList<>(); // Thường suy luận ArrayList<Object>
values.add("An");
values.add(42);                           // Cũng có thể hợp lệ do phần tử là Object
```

Nếu ý định là danh sách `String`, viết `var values = new ArrayList<String>();` (với import phù hợp) hoặc `List<String> values = new ArrayList<>();`. Những lần `add` hoặc gán phía sau **không làm trình biên dịch tính lại** generic type của biến.

## 6. `null`, `final` và những điểm dễ nhầm

### 6.1. `null` không xác định kiểu ở initializer

```java
// var text = null; // Không hợp lệ: không suy luận được kiểu từ literal null

var text = "hello"; // String
text = null;        // Hợp lệ: kiểu tĩnh vẫn String

String otherText = null; // Hợp lệ: đã có kiểu tường minh
```

Với biến kiểu nguyên thủy như `int` hoặc `boolean`, `null` không thể là giá trị của biến.

### 6.2. `final var` cấm gán lại, không tự khóa đối tượng

```java
final var names = new java.util.ArrayList<String>();
names.add("An"); // Hợp lệ: đối tượng ArrayList vẫn thay đổi được
// names = new java.util.ArrayList<String>(); // Lỗi: không được gán lại biến final
```

`final` điều khiển khả năng **gán lại biến**. `var` điều khiển cách **viết kiểu khi khai báo**. Hai tính chất độc lập.

### 6.3. Phép `+=` có quy tắc khác `=`

Với kiểu số, phép gán kết hợp có thể thực hiện chuyển đổi ngầm theo quy tắc riêng của Java:

```java
var count = 5;   // int
count += 2.8;    // Hợp lệ: kết quả phép cộng được chuyển về int, count là 7
// count = count + 2.8; // Lỗi: kết quả cộng có kiểu double
```

Điều này **không** có nghĩa kiểu của `count` đổi thành `double` rồi quay về `int`. Kiểu `count` từ đầu tới cuối là `int`. Với dữ liệu tiền, đo lường hoặc phép tính có phần thập phân, tránh dùng `+=` theo cách gây mất phần thập phân không chủ ý.

## 7. Ví dụ Java 17+ có thể biên dịch và chạy

Tạo tệp **`ReassignmentTypeDemo.java`** với nội dung đầy đủ sau:

```java
import java.util.ArrayList;
import java.util.LinkedList;
import java.util.List;

public class ReassignmentTypeDemo {
    interface Pet {
        String speak();
    }

    static final class Dog implements Pet {
        @Override
        public String speak() {
            return "woof";
        }
    }

    static final class Cat implements Pet {
        @Override
        public String speak() {
            return "meow";
        }
    }

    public static void main(String[] args) {
        var count = 1;                // int
        count = 5;                    // int

        var distance = 10L;           // long
        distance = 3;                 // int -> long

        var price = 10.0;             // double
        price = 7;                    // int -> double

        var label = "initial";        // String
        label = null;                 // String, gia tri null

        var names = new ArrayList<String>(List.of("An"));
        names = new ArrayList<String>(List.of("Binh"));
        names.add("Lan");             // Thay doi object, khong gan lai

        List<String> queue = new ArrayList<>();
        queue = new LinkedList<>(List.of("Nam"));

        Pet pet = new Dog();
        var firstSound = pet.speak(); // String
        pet = new Cat();             // Kieu tinh van la Pet

        System.out.println("count=" + count);
        System.out.println("distance=" + distance);
        System.out.println("price=" + price);
        System.out.println("labelNull=" + (label == null));
        System.out.println("names=" + names);
        System.out.println("queue=" + queue);
        System.out.println("firstSound=" + firstSound);
        System.out.println("currentSound=" + pet.speak());
        System.out.println("runtimeClass=" + pet.getClass().getSimpleName());
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 ReassignmentTypeDemo.java
java ReassignmentTypeDemo
```

**Đầu ra chính xác:**

```text
count=5
distance=3
price=7.0
labelNull=true
names=[Binh, Lan]
queue=[Nam]
firstSound=woof
currentSound=meow
runtimeClass=Cat
```

**Phân tích:**

1. `count` là `int` cả trước và sau khi nhận `5`.
2. `distance` là `long` dù biểu thức gán tiếp theo là `int`; `price` là `double` dù nhận `int`.
3. `label` giữ kiểu `String` sau khi nhận `null`.
4. `names` là `ArrayList<String>`; phép gán mới tạo một `ArrayList` khác. `add` chỉ thay đổi nội dung đối tượng hiện tại.
5. `queue` có kiểu `List<String>` nên được đổi từ `ArrayList` sang `LinkedList`.
6. `pet` có kiểu tĩnh `Pet`; lớp runtime lần lượt là `Dog` rồi `Cat`, dẫn đến kết quả `speak()` khác nhau. `firstSound` là chuỗi được lấy trước khi gán lại `pet`, nên vẫn là `"woof"`.

Không cần dựa vào thứ tự duyệt của một `Map` hoặc vào giá trị ngẫu nhiên để xác định stdout trong ví dụ này.

## 8. Những trường hợp biên dịch lỗi và cách sửa

Các đoạn sau **cố ý chứa lỗi** để nhận diện sai lầm; không thêm trực tiếp chúng vào chương trình chạy ở mục 7.

### Lỗi A: Tưởng `var` đổi kiểu theo giá trị mới

```java
var x = 100;   // int
x = "100";     // Lỗi: String không gán được cho int
```

**Sửa:** Nếu biến thực sự chứa văn bản, chọn `String x = "100";` ngay từ đầu. Nếu cần cả số và chữ tùy thời điểm, hãy thiết kế API và kiểu dữ liệu rõ ràng; sử dụng `Object` chỉ khi nhu cầu đa kiểu là có chủ đích.

### Lỗi B: Tưởng `var` sẽ tự mở rộng `int` thành `long`

```java
var duration = 1; // int
duration = 10L;   // Lỗi: long -> int không được gán ngầm
```

**Sửa:** `var duration = 1L;` hoặc `long duration = 1;`.

### Lỗi C: Tưởng hai implementation của cùng interface gán thay thế cho mọi biến

```java
var list = new java.util.ArrayList<String>();
list = new java.util.LinkedList<String>(); // Lỗi
```

**Sửa:** `List<String> list = new ArrayList<>();` (có import) nếu muốn linh hoạt đổi implementation.

### Lỗi D: Nhầm `final` với tính bất biến của đối tượng

```java
final var list = new java.util.ArrayList<String>();
list.add("ok");                            // Hợp lệ
list = new java.util.ArrayList<String>();  // Lỗi: final
```

**Sửa:** Chỉ dùng `final` khi muốn ngăn gán lại. Muốn hạn chế sửa nội dung, cần lựa chọn cấu trúc dữ liệu hoặc API có quy tắc bất biến phù hợp.

### Lỗi E: Tưởng thay đổi runtime class cũng mở thêm phương thức trên kiểu tĩnh

```java
Object value = "Java";
value = new java.util.ArrayList<String>();
// value.add("An"); // Lỗi: Object không khai báo phương thức add
```

**Sửa:** Sử dụng kiểu/interface có các thao tác thật sự cần thiết hoặc kiểm tra kiểu trước khi xử lý những thao tác đặc thù.

## 9. Chọn `var` hay kiểu tường minh khi sẽ gán lại?

Xét nhu cầu thực tế trước khi viết khai báo:

| Tình huống | Cách khai báo gợi ý | Vì sao |
| --- | --- | --- |
| Biến đếm cục bộ và nguồn kiểu rõ | `var count = 0;` | `int` rõ từ initializer, phạm vi nhỏ. |
| Biến cần `long` cho phép tính hoặc API | `long size = 0;` hoặc `var size = 0L;` | Bảo toàn kiểu mong muốn ngay lúc khai báo. |
| Chỉ thay đối tượng bằng instance cùng lớp | `var builder = new StringBuilder();` | Kiểu lớp cụ thể rõ ràng từ constructor. |
| Muốn đổi `ArrayList` sang `LinkedList` | `List<String> list = new ArrayList<>();` | Thể hiện interface làm hợp đồng kiểu. |
| Muốn nhận nhiều implementation của `Pet` | `Pet pet = new Dog();` | Kiểu tĩnh đủ rộng và ý định dễ thấy. |
| Không muốn gán lại biến | `final var name = "A";` | Giữ kiểu suy luận, đồng thời cấm gán lại. |
| Kiểu trả về của initializer mơ hồ | Kiểu tường minh (ví dụ `List<Item> items = loadItems();`) | Giảm công tra cứu và tránh hiểu nhầm về kiểu. |

Nguyên tắc: **chọn kiểu khai báo để diễn đạt hợp đồng bạn muốn duy trì trong toàn bộ phạm vi của biến**. Khi cần đổi giá trị, hãy kiểm tra tính tương thích với hợp đồng này. Việc dùng `var` chỉ là cách để trình biên dịch viết hộ tên kiểu ban đầu.

### Checklist khi đọc hoặc review code

1. Xác định **biểu thức khởi tạo** của biến `var`.
2. Tìm **kiểu tĩnh** được suy luận tại dòng khai báo, bao gồm generic và loại literal số.
3. Với từng phép gán lại, xét **assignment conversion** sang **kiểu tĩnh ban đầu**.
4. Nếu gán một đối tượng khác, phân biệt **lớp runtime** với **kiểu tĩnh**.
5. Nếu sẽ thay implementation, cân nhắc khai báo bằng **interface/kiểu cha** tường minh.
6. Phân biệt **gán lại tham chiếu**, **thay đổi trạng thái đối tượng** và **gán `null`**.
7. Nếu gặp `final` hoặc `+=`, áp dụng quy tắc riêng của chúng; không suy diễn rằng `var` cho phép đổi kiểu.

## 10. Tự kiểm tra

**Câu 1.** Sau đoạn code `var x = 1; x = 2;`, kiểu của `x` là gì?

**Câu 2.** `var x = 1L; x = 2;` có biên dịch được không? Kiểu của `x` sau phép gán là gì?

**Câu 3.** `var x = "Hello"; x = null;` có biên dịch được không? Kiểu của `x` là gì?

**Câu 4.** `var items = new ArrayList<String>(); items = new LinkedList<String>();` (đã import hai lớp) có biên dịch không? Viết lại để đổi implementation hợp lệ.

**Câu 5.** Với `Pet pet = new Dog(); pet = new Cat();` và cả hai lớp đều triển khai `Pet`, kiểu tĩnh và lớp runtime của `pet` sau lệnh thứ hai là gì?

**Câu 6.** Vì sao `var count = 3; count += 2.5;` biên dịch, còn `count = count + 2.5;` lại không? `count` thuộc kiểu nào sau đó?

**Câu 7.** Với `final var names = new ArrayList<String>();`, câu `names.add("Lan");` và `names = new ArrayList<String>();` khác nhau thế nào?

**Đáp án:**

1. `int`. Giá trị đổi, kiểu không đổi.
2. Có. `int` được mở rộng sang `long` khi gán; `x` luôn là `long`.
3. Có. `x` vẫn có kiểu `String`; `null` hợp lệ với tham chiếu.
4. Không, vì kiểu suy luận là `ArrayList<String>`. Dùng `List<String> items = new ArrayList<>(); items = new LinkedList<>();`.
5. Kiểu tĩnh `Pet`; đối tượng hiện tại có lớp runtime `Cat`.
6. Gán kết hợp `+=` có quy tắc chuyển kết quả về kiểu biến; phép gán thường `=` không tự thu hẹp kết quả `double` về `int`. `count` vẫn là `int` (giá trị `5`).
7. `add` sửa nội dung đối tượng nên hợp lệ; `names = ...` gán lại biến `final` nên lỗi.

## 11. Tóm lược và nguồn chuẩn

- **Suy luận kiểu của `var` chỉ xảy ra tại khai báo.**
- **Mọi lần gán lại phải tương thích với kiểu tĩnh đã cố định.**
- **Giá trị, đối tượng runtime và kiểu tĩnh là ba khái niệm khác nhau.**
- **Chuyển đổi kiểu lúc gán không phải suy luận lại kiểu.**
- **Khi cần đổi giữa các implementation, khai báo interface/kiểu cha nếu phù hợp.**
- **`final` kiểm soát việc gán lại; tính mutable của đối tượng là chuyện riêng.**

Đọc thêm các tài liệu vẫn còn giá trị áp dụng:
- [JEP 286 — Local-Variable Type Inference](https://openjdk.org/jeps/286): cách `var` suy luận kiểu từ initializer.
- [OpenJDK / Project Amber — FAQ về `var`](https://github.com/openjdk/amber-docs/blob/master/site/guides/lvti-faq.md): trả lời trực tiếp câu hỏi về biến có nhiều phép gán.
- [Java Language Specification `14.4 — Local Variable Declarations](https://docs.oracle.com/javase/specs/jls/se26/html/jls-14.html#jls-14.4): khai báo biến cục bộ và suy luận kiểu.
- [Java Language Specification `5.2 — Assignment Contexts](https://docs.oracle.com/javase/specs/jls/se26/html/jls-5.html#jls-5.2): các chuyển đổi hợp lệ trong phép gán.
- [Java Language Specification `15.26 — Assignment Operators](https://docs.oracle.com/javase/specs/jls/se26/html/jls-15.html#jls-15.26): phép `=` và các phép gán kết hợp.
