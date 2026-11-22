# Vì sao đọc từ `List<? super T>` chỉ được bảo đảm là `Object`?

## 1. Vấn đề cần hiểu

Trong Java generics, wildcard giới hạn dưới `? super T` (*lower-bounded wildcard*) biểu thị **một kiểu chưa biết nhưng là `T` hoặc một supertype của `T`**. Ví dụ, `List<? super Integer>` có thể tham chiếu đến `List<Integer>`, `List<Number>`, `List<Object>` hoặc danh sách tham số hóa bằng một supertype hợp lệ khác của `Integer`.

Ta có thể **thêm `Integer`** an toàn vào các danh sách đó, vì mọi kiểu phần tử khả dĩ đều chấp nhận `Integer`. Nhưng khi **đọc** bằng `get(...)`, compiler không biết danh sách thực tế chứa `Integer`, `Number`, `Object` hay giá trị thuộc một loại rộng hơn. Với `java.util.List<E>`, giới hạn trên khai báo của `E` là `Object`, nên kiểu đọc bảo đảm duy nhất là **`Object`**.

~~~java
List<Number> numbers = new ArrayList<>();
List<? super Integer> destination = numbers;

destination.add(42);            // Được: Integer phù hợp với mọi supertype của Integer.
Object item = destination.get(0); // Được: giới hạn trên an toàn là Object.
// Integer exact = destination.get(0); // Lỗi biên dịch.
~~~

Đây là điểm khác biệt quan trọng giữa **kiểu phần tử có thể ghi vào** và **kiểu phần tử có thể suy ra khi đọc ra**. Bài học giải thích chính xác nguyên nhân, các trường hợp dễ nhầm và cách dùng trong API Java 17 trở lên.

## 2. Một biến `List<? super Integer>` có thể trỏ đến những danh sách nào?

Xem các khai báo độc lập sau:

~~~java
List<Integer> integers = new ArrayList<>();
List<Number> numbers = new ArrayList<>();
List<Object> objects = new ArrayList<>();

List<? super Integer> a = integers;
List<? super Integer> b = numbers;
List<? super Integer> c = objects;
~~~

Ba phép gán đều hợp lệ vì `Integer` có thể được sử dụng ở nơi cần `Integer`, `Number` hoặc `Object`. Có thể có thêm các supertype khác, chẳng hạn interface mà `Integer` thực thi. Wildcard không chọn một trong các kiểu ấy tại thời điểm biên dịch; nó **che kiểu phần tử cụ thể** khỏi code đang dùng biến `List<? super Integer>`.

Hãy tưởng tượng danh sách thực sự là:

~~~java
List<Object> objects = new ArrayList<>();
objects.add("text");                // String là Object.
objects.add(Integer.valueOf(99));   // Integer cũng là Object.

List<? super Integer> view = objects;
Object first = view.get(0);         // Giá trị thực tế là String.
~~~

Nếu compiler tự cho phép `Integer first = view.get(0)` thì chương trình sẽ nhận một `String` như `Integer`, làm sai bảo đảm tĩnh của generics. Java không cho phép phép gán ấy. Khả năng **thêm** `Integer` không suy ra rằng **mọi phần tử có sẵn** đều là `Integer`.

**Điều quan trọng:** `List<? super Integer>` không có nghĩa “list chỉ chứa số nguyên”. Nó là *một góc nhìn* có thể ghi số nguyên vào các list có kiểu phần tử thuộc một supertype hợp lệ của `Integer`.

## 3. Lập luận kiểu: giới hạn dưới giúp ghi, giới hạn trên quyết định đọc

`List<E>` khai báo tham số kiểu `E` không có bound tường minh, vì vậy bound mặc định của `E` là `Object`.

Khi compiler gặp `List<? super Integer>`, quy tắc **capture conversion** của Java có thể mô hình hóa wildcard bằng một kiểu ẩn, tạm gọi `CAP#1`:

~~~text
Integer <: CAP#1 <: Object
~~~

Đây là **sơ đồ quan hệ kiểu**, không phải cú pháp khai báo Java. Ký hiệu `A <: B` nói rằng `A` là subtype của `B`.

- **Giới hạn dưới `Integer`** bảo đảm mọi giá trị `Integer` đều gán được cho `CAP#1`. Vì vậy `destination.add(42)` có thể biên dịch.
- **Giới hạn trên `Object`** bảo đảm mọi giá trị thuộc `CAP#1` đều có thể được đọc như `Object`.
- Không có ràng buộc nào bảo đảm `CAP#1 <: Number` hoặc `CAP#1 <: Integer`. Do đó `Number n = destination.get(0)` và `Integer i = destination.get(0)` không được phép.

Hãy gắn lập luận này vào chữ ký của `List<E>`:

~~~java
E get(int index);
boolean add(E element);
E set(int index, E element);
~~~

Đây là các **chữ ký rút gọn** để giải thích kiểu, không phải ba phương thức độc lập cần đem biên dịch. Sau capture conversion:

- `get` trả về `CAP#1`, có thể **nâng lên `Object`** mà không cần cast.
- `add` cần một giá trị `CAP#1`; compiler cho phép truyền `Integer` nhờ `Integer <: CAP#1`.
- `set` nhận `Integer` an toàn nhưng giá trị cũ mà nó trả về vẫn chỉ có thể được dùng như `Object`.

Chẳng hạn:

~~~java
List<? super Integer> sink = new ArrayList<Number>();
sink.add(5);
Object old = sink.set(0, 7);
Object current = sink.get(0);

// Không hợp lệ: không biết kiểu CAP#1 chính xác.
// Integer oldInt = sink.set(0, 9);
// Number currentNumber = sink.get(0);
~~~

**Quy tắc đọc thực sự phụ thuộc vào *giới hạn trên* của type variable trong generic class, không phải chỉ vào chữ `super`.** Với `List<E>`, giới hạn đó là `Object`. Một ví dụ generic class có bound `E extends Number` sẽ được xét riêng ở mục 8.

## 4. So sánh `extends`, `super` và wildcard không giới hạn

| Kiểu view | Một số kiểu nguồn phù hợp | Kiểu an toàn khi `get(0)` | Có thể `add(new Integer(1))` về mặt kiểu? |
| --- | --- | --- | --- |
| `List<Integer>` | `List<Integer>` | `Integer` | Có |
| `List<? extends Number>` | `List<Integer>`, `List<Double>`, `List<Number>` | `Number` | Không |
| `List<? super Integer>` | `List<Integer>`, `List<Number>`, `List<Object>` | `Object` | Có |
| `List<?>` | `List<String>`, `List<Integer>`, v.v. | `Object` | Không (trừ `null`) |
| `List<Object>` | `List<Object>` | `Object` | Có |

Trong bảng, “có thể add” chỉ nói **compiler cho phép thao tác theo kiểu**. Nếu implementation là danh sách không sửa được như `List.of(...)`, `add` vẫn có thể ném `UnsupportedOperationException` lúc chạy.

Đối chiếu ba ví dụ nhỏ:

~~~java
List<Integer> ints = new ArrayList<>();

List<? extends Number> producer = ints;
Number readNumber = producer.get(0); // Hợp lệ về kiểu (nhưng list phải có phần tử).
// producer.add(5);                  // Không hợp lệ.

List<? super Integer> consumer = ints;
consumer.add(5);                     // Hợp lệ.
Object readObject = consumer.get(0);  // Hợp lệ.
// Integer readInteger = consumer.get(0); // Không hợp lệ.

List<?> unknown = ints;
Object any = unknown.get(0);         // Hợp lệ.
// unknown.add(5);                   // Không hợp lệ.
~~~

Vì `ints` bắt đầu là list rỗng, **đừng chạy `get(0)` trước khi một phần tử được thêm vào**; khối trên nhằm minh họa hệ thống kiểu theo từng dòng, không phải chương trình hoàn chỉnh chạy theo thứ tự. Mã chạy độc lập với phần tử hợp lệ nằm ở mục 7.

PECS (*Producer Extends, Consumer Super*) tóm tắt hai trường hợp sử dụng thường gặp:

- Khi cần **đọc các giá trị như một loại cha cụ thể**, chọn `? extends T`.
- Khi cần **ghi các giá trị `T` hoặc subtype của `T`**, chọn `? super T`.

PECS không có nghĩa `? super T` bị cấm đọc; ta vẫn đọc được, nhưng thường chỉ có một `Object` khi generic declaration không chỉ định bound hẹp hơn.

## 5. Vì sao “tôi vừa thêm Integer” vẫn không đổi kiểu đọc thành Integer?

Một ví dụ trực giác:

~~~java
List<Number> numbers = new ArrayList<>();
numbers.add(1.5);

List<? super Integer> sink = numbers;
sink.add(42);

Object first = sink.get(0);  // Double thực tế.
Object second = sink.get(1); // Integer thực tế.
~~~

Biến `sink` có **một kiểu khai báo duy nhất**. Compiler không thiết lập quy tắc rằng các vị trí sau một lời gọi `add(Integer)` chắc chắn luôn chứa `Integer`:

- List có thể **đã có phần tử cũ** thuộc supertype rộng hơn.
- List có thể được sửa thông qua **reference khác** như `numbers`, cũng trỏ cùng đối tượng.
- Chỉ số phần tử và trạng thái list có thể thay đổi qua các thao tác khác; compiler không theo dõi xuất xứ/kiểu runtime của từng vị trí trong collection tổng quát.
- Một danh sách dưới view `List<? super Integer>` có thể chứa các đối tượng `Number`, `Object` tùy generic argument thật sự.

Nếu bạn vẫn giữ chính đối tượng `Integer` đã thêm và muốn dùng nó, hãy dùng biến đã có kiểu:

~~~java
Integer added = 42;
sink.add(added);
Integer retained = added; // Không cần đọc lại từ view.
~~~

Nếu cần đọc phần tử như `Number` và bạn **biết chắc danh sách nguồn** có kiểu `List<Number>`, hãy dùng reference có thông tin chính xác hơn:

~~~java
List<Number> typed = new ArrayList<>();
List<? super Integer> sink = typed;

sink.add(42);
Number n = typed.get(0); // Hợp lệ nhờ kiểu khai báo List<Number> của typed.
Object o = sink.get(0);  // Chỉ Object qua view List<? super Integer>.
~~~

Hai biến cùng chỉ một list, nhưng **hợp đồng kiểu tĩnh** ở từng biểu thức khác nhau. Phép đọc dùng `sink` không tự thừa hưởng mọi tri thức của biến `typed`.

## 6. Đọc an toàn: dùng `Object` rồi kiểm tra khi cần subtype

Với `List<? super Integer>`, dạng tổng quát là:

~~~java
List<? super Integer> values = new ArrayList<Object>();
values.add(10);
Object value = values.get(0);
System.out.println(value);
~~~

Nếu thuật toán thực sự cần thao tác số học, hãy **kiểm tra đối tượng được đọc tại runtime**:

~~~java
Object value = values.get(0);
if (value instanceof Integer integer) {
    System.out.println(integer + 1);
} else if (value instanceof Number number) {
    System.out.println(number.doubleValue());
} else {
    System.out.println("Không phải số nguyên hoặc Number");
}
~~~

Pattern matching cho `instanceof` ở ví dụ trên được hỗ trợ từ Java 16 và dùng ổn định với Java 17. Nó chứng minh kiểu **của đối tượng riêng lẻ đang được kiểm tra**, không chứng minh mọi phần tử của danh sách đều là `Integer`.

Có thể dùng checked cast:

~~~java
Object value = values.get(0);
Integer integer = (Integer) value; // Chỉ thành công nếu object là Integer hoặc null.
~~~

Nếu thực tế là `Double` hoặc `String`, cast ném `ClassCastException`; nếu là `null`, cast trả về `null`. Nên dùng `instanceof` khi dữ liệu có thể thuộc nhiều kiểu. **Cast không biến `List<? super Integer>` thành `List<Integer>`.**

Không viết:

~~~java
List<? super Integer> values = new ArrayList<Object>();
// KHÔNG biên dịch: kiểu trả về CAP#1 chỉ bảo đảm là Object.
Integer integer = values.get(0);

// KHÔNG biên dịch vì List<? super Integer> không bảo đảm là List<Integer>.
List<Integer> exactList = values;
~~~

Lỗi ở compile time nhằm ngăn caller tự suy ra một subtype chỉ từ giới hạn dưới.

## 7. Chương trình hoàn chỉnh Java 17+: ghi Integer và đọc dưới dạng Object

Lưu tệp với tên **SuperReadDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class SuperReadDemo {
    static final class NumberBox<T extends Number> {
        private T value;
        NumberBox(T value) { this.value = value; }
        T get() { return value; }
        void set(T value) { this.value = value; }
    }

    static void appendInteger(List<? super Integer> destination, Integer value) {
        destination.add(value);
    }

    public static void main(String[] args) {
        List<Number> numbers = new ArrayList<>();
        numbers.add(1.5);
        List<? super Integer> output = numbers;
        appendInteger(output, 10);
        Object first = output.get(0);
        Object last = output.get(1);
        System.out.println("first: " + first);
        System.out.println("last: " + last);
        System.out.println("numbers: " + numbers);

        List<Object> mixed = new ArrayList<>();
        mixed.add("text");
        List<? super Integer> sameTypeOfView = mixed;
        sameTypeOfView.add(7);
        Object item = sameTypeOfView.get(0);
        System.out.println("mixed first: " + item);
        if (sameTypeOfView.get(1) instanceof Integer value) {
            System.out.println("checked integer: " + value);
        }
        System.out.println("mixed: " + mixed);

        NumberBox<Number> numberBox = new NumberBox<>(3.5);
        NumberBox<? super Integer> boxView = numberBox;
        Number before = boxView.get();
        boxView.set(9);
        System.out.println("bounded read: " + before);
        System.out.println("bounded after: " + boxView.get());
    }
}
~~~

Biên dịch và chạy (Java 17+):

~~~bash
javac --release 17 -Xlint:all SuperReadDemo.java
java SuperReadDemo
~~~

**Stdout chính xác**:

~~~text
first: 1.5
last: 10
numbers: [1.5, 10]
mixed first: text
checked integer: 7
mixed: [text, 7]
bounded read: 3.5
bounded after: 9
~~~

Chương trình đã được kiểm tra bằng `javac --release 17 -Xlint:all` và chạy thành công, **không phát sinh unchecked warning**.

Giải thích:

1. `output` có kiểu `List<? super Integer>` và được gán từ `List<Number>`; `appendInteger` thêm `10` an toàn.
2. Dù đã thêm `Integer`, `output.get(0)` và `output.get(1)` đều được đọc vào biến `Object`. Phần tử đầu thực tế là `Double 1.5` và phần tử sau là `Integer 10`.
3. `sameTypeOfView` có **cùng kiểu tĩnh** `List<? super Integer>` nhưng trỏ đến `List<Object>` có sẵn `String "text"`. Đây là phản ví dụ trực tiếp cho suy đoán rằng đọc từ `? super Integer` luôn ra `Integer`.
4. `instanceof Integer value` kiểm tra đúng phần tử thứ hai rồi mới sử dụng như `Integer`.
5. `NumberBox<? super Integer>` được đọc như `Number` vì tham số kiểu **của chính `NumberBox<T extends Number>`** có giới hạn trên `Number`, như mục tiếp theo.

## 8. Ngoại lệ quan trọng: generic class có upper bound hẹp hơn `Object`

Nói “`? super T` luôn chỉ được đọc như `Object`” là **quá tổng quát**. Quy tắc chính xác là: kiểu capture có **giới hạn trên từ tham số kiểu của generic declaration**; kết quả đọc tối thiểu dựa trên bound ấy.

Với `List<E>`, `E` có upper bound mặc định `Object`, nên `List<? super Integer>.get()` không có đảm bảo mạnh hơn `Object`.

Nhưng với class tự khai báo:

~~~java
static final class NumberBox<T extends Number> {
    private T value;

    NumberBox(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }

    void set(T value) {
        this.value = value;
    }
}
~~~

`NumberBox<? super Integer>` có capture type `CAP#2` thỏa:

~~~text
Integer <: CAP#2 <: Number
~~~

Vì **upper bound là `Number`**, có thể đọc an toàn như `Number`:

~~~java
NumberBox<Number> actual = new NumberBox<>(3.5);
NumberBox<? super Integer> view = actual;

view.set(42);             // Integer là subtype của CAP#2.
Number n = view.get();    // Hợp lệ: CAP#2 chắc chắn là Number.
// Integer i = view.get(); // Không hợp lệ: CAP#2 có thể là Number.
~~~

Hai khối trên là **trích đoạn minh họa cần đặt trong cùng một lớp và import/type context phù hợp**, còn chương trình mục 7 là ví dụ chạy độc lập.

Quy tắc JLS về capture conversion còn xét bound và các ràng buộc của generic declaration khác; dạng `T extends Number` là trường hợp dễ quan sát nhất. Vì vậy **đọc ra `Object` là kết luận đúng cho `List<? super T>` và các generic type có parameter bound là `Object`**, nhưng phải kiểm tra upper bound khi dùng generic class khác.

## 9. Viết API theo hướng consumer: khi nào chọn `? super T`?

### 9.1. Hàm đẩy dữ liệu vào list đích

~~~java
static void addDefaults(List<? super Integer> target) {
    target.add(10);
    target.add(20);
}
~~~

Có thể gọi hàm này với `List<Integer>`, `List<Number>` hoặc `List<Object>`, miễn implementation cho phép sửa. Hàm chỉ cần biết rằng **Integer là kiểu được chấp nhận khi ghi**. Nó không phải đọc từ list rồi thực hiện phép toán `Integer`.

### 9.2. Đối chiếu nguồn `extends` và đích `super`

~~~java
static <T> void copyValues(List<? extends T> source, List<? super T> target) {
    for (T element : source) {
        target.add(element);
    }
}
~~~

Đây là một phương thức minh họa có thể đặt trong lớp Java sau khi import `java.util.List`. Ví dụ:

~~~java
List<Integer> source = List.of(1, 2, 3);
List<Number> target = new ArrayList<>();
copyValues(source, target);
~~~

`source` **cung cấp** các `T`; `target` **nhận** các `T`. Chữ ký tách hai mục tiêu và không yêu cầu đọc `Integer` từ một `List<? super Integer>`. Trước khi dùng mẫu này trong production, hãy xét hợp đồng về danh sách có thể sửa được, `null` và xử lý khi nguồn/đích có thể bị cập nhật đồng thời.

API chuẩn `Collections.copy(List<? super T> dest, List<? extends T> src)` sử dụng chính nguyên tắc này; nó còn có yêu cầu kích thước đích đủ lớn (khác với việc append ở ví dụ `copyValues`). Đừng tự coi mọi “copy” đều có nghĩa thêm phần tử vào cuối.

### 9.3. Không dùng `? super` khi cần trả về subtype chính xác

Nếu mục tiêu là lấy `Integer` để tính toán, hãy nhận một nguồn có kiểu thích hợp:

~~~java
static int sumIntegers(List<Integer> values) {
    int total = 0;
    for (Integer value : values) {
        total += value;
    }
    return total;
}
~~~

Hoặc nếu muốn xử lý cả các loại số khác:

~~~java
static double sumNumbers(List<? extends Number> values) {
    double total = 0.0;
    for (Number value : values) {
        total += value.doubleValue();
    }
    return total;
}
~~~

Dùng `? super Integer` cho một tham số chỉ để **đọc các số nguyên** sẽ đưa ra hợp đồng quá rộng về dữ liệu và quá yếu về kiểu kết quả.

## 10. Các thao tác khác trên `List<? super Integer>`

| Thao tác | Compiler cho phép? | Ý nghĩa |
| --- | --- | --- |
| `destination.add(3)` | Có | `Integer` gán được cho kiểu capture. |
| `destination.add(Integer.valueOf(3))` | Có | Bổ sung một `Integer`. |
| `destination.add(3.5)` | Không | `Double` không được bảo đảm phù hợp với mọi loại list đích. |
| `destination.add((Number) 3)` | Không | Biến `Number` có thể chứa loại không phải `Integer`. |
| `destination.add(null)` | Có về kiểu | `null` có thể được truyền cho kiểu tham chiếu; collection cụ thể có thể không chấp nhận null. |
| `Object x = destination.get(0)` | Có | Giới hạn trên của `List<E>` là `Object`. |
| `Integer x = destination.get(0)` | Không | Không bảo đảm capture là subtype của `Integer`. |
| `Number x = destination.get(0)` | Không | Capture có thể là `Object`. |
| `Object x = destination.set(0, 7)` | Có về kiểu | Ghi `Integer`, đọc phần tử cũ như `Object`. |
| `destination.remove(0)` | Có về kiểu | Xóa theo chỉ số, không cần cung cấp một kiểu phần tử cụ thể. |
| `destination.clear()` | Có về kiểu | Xóa toàn bộ; implementation có thể cấm sửa. |

Một số phương thức trả về kiểu không liên quan tới `E`, chẳng hạn `size()` trả về `int` và `contains(Object)` trả về `boolean`. Cụm “đọc chỉ bảo đảm là Object” đề cập cụ thể tới **đọc một giá trị thuộc type parameter `E`** bằng `get`, `iterator().next()`, `set` trả về phần tử cũ, v.v., không phải mọi phương thức của `List`.

## 11. Lỗi thường gặp và cách sửa

**Lỗi 1 — Đồng nhất `? super Integer` với `List<Integer>`.**

~~~java
List<? super Integer> target = new ArrayList<Number>();
// Integer n = target.get(0); // Không biên dịch.
~~~

Sửa bằng cách nhận giá trị như `Object`, dùng `instanceof` nếu cần phân nhánh theo kiểu thực tế, hoặc thay đổi hợp đồng method nếu thuật toán đòi `Integer`.

**Lỗi 2 — Suy ra kiểu đọc từ giá trị vừa `add`.** Java không theo dõi được mọi phần tử trong một container theo thứ tự thêm ở cấp kiểu. Giữ reference `Integer` ban đầu, hoặc dùng view chính xác hơn khi có chứng cứ.

**Lỗi 3 — Ép `(Integer) list.get(0)` mà không kiểm tra dữ liệu.** Cast này có thể phát sinh `ClassCastException` nếu phần tử là `Double` hoặc `String`. Nó cũng không thay đổi loại generic của danh sách.

**Lỗi 4 — Ép kiểu cả collection:**

~~~java
List<? super Integer> view = new ArrayList<Object>();
// Không nên cố biến toàn bộ danh sách thành List<Integer>
// qua raw cast hoặc unchecked cast để lấy kiểu phần tử chính xác hơn.
~~~

Việc dùng raw type hoặc unchecked cast chỉ che đi rủi ro, có thể tạo heap pollution. Nếu cần collection `List<Integer>`, hãy kiểm tra từng giá trị và tạo collection mới với type argument xác định.

**Lỗi 5 — Nghĩ `? super Number` có thể đọc `Number`.** Đối với `List<E>`:

~~~java
List<? super Number> list = new ArrayList<Object>();
list.add(3.5);          // Hợp lệ: Double là Number.
Object value = list.get(0); // Kiểu đọc vẫn chỉ bảo đảm Object.
// Number n = list.get(0);  // Không biên dịch.
~~~

Giới hạn dưới `Number` giúp thêm `Number` và subtype; nó **không** tự nâng giới hạn trên của `List<E>` khỏi `Object`.

**Lỗi 6 — Quên rằng generic view không quyết định list có sửa được.** `List<? super Integer> view = List.<Integer>of(1, 2);` hợp lệ, nhưng `view.add(3)` sẽ ném `UnsupportedOperationException` lúc chạy vì `List.of` tạo danh sách không sửa được. Đây là vấn đề hợp đồng mutability, không phải lỗi giới hạn kiểu.

## 12. Tự kiểm tra kiến thức

1. `List<? super Integer>` có thể nhận tham chiếu đến `List<Object>` không? **Có**, vì `Object` là supertype của `Integer`.
2. Vì sao `target.add(12)` hợp lệ? **Vì `Integer` là subtype của mọi kiểu phần tử phù hợp với `? super Integer`.**
3. Vì sao `Integer x = target.get(0)` không hợp lệ? **Vì kiểu phần tử thực tế có thể là `Number`, `Object` hay supertype khác; compiler chỉ biết giới hạn trên của `List<E>` là `Object`.**
4. Đã thêm một `Integer` thì có thể đọc mọi phần tử như `Integer` không? **Không.** Danh sách có thể đã chứa giá trị thuộc kiểu rộng hơn và được sửa qua reference khác.
5. Có thể dùng `instanceof Integer` cho giá trị đọc ra không? **Có.** Kiểm tra đó chỉ bảo đảm kiểu cho giá trị đang xét khi điều kiện đúng.
6. Có phải `? super T` luôn chỉ đọc được như `Object` trong mọi generic class? **Không.** Với `Box<E extends Number>` và `Box<? super Integer>`, đọc được dưới dạng `Number`.
7. Muốn nhận một danh sách để đọc mọi `Number`, nên chọn `List<? extends Number>` hay `List<? super Number>`? **`List<? extends Number>`**, vì bảo đảm từng phần tử đọc được như `Number`.

## 13. Tài liệu tham khảo

- [JLS Java SE 17 §4.5.1 — Type Arguments of Parameterized Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5.1): wildcard giới hạn dưới/giới hạn trên và containment.
- [JLS Java SE 17 §5.1.10 — Capture Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.10): capture type của `? super T`, lower bound và upper bound từ generic declaration.
- [JLS Java SE 17 §4.10.2 — Subtyping Among Class and Interface Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.10.2): quan hệ subtyping khi dùng parameterized types.
- [Java SE 17 API — List<E>](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html): chữ ký `add(E)`, `get(int)`, `set(int,E)` và ngoại lệ có thể phát sinh.
- [Java SE 17 API — Collections.copy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#copy(java.util.List,java.util.List)): ví dụ thực tế dùng `? super T` ở đích và `? extends T` ở nguồn.
