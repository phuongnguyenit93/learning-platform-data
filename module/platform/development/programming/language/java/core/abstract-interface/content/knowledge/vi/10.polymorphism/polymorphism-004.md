# Chọn overload lúc biên dịch và chọn override lúc chạy trong Java

Trong Java, một lời gọi phương thức có thể đi qua **hai quyết định khác nhau**:

1. **Overload resolution (chọn phương thức nạp chồng)**: trình biên dịch chọn **chữ ký phương thức** phù hợp với *kiểu tĩnh* của biểu thức nhận lời gọi, *kiểu tĩnh* của các đối số và các quy tắc chuyển đổi tham số.
2. **Override dispatch (phân phối phương thức ghi đè)**: với phương thức instance cho phép đa hình, JVM chọn **phần triển khai** của chữ ký đã chọn theo *lớp thực tế của đối tượng nhận lời gọi* lúc chạy.

Vì vậy, câu dễ nhớ là **overload chọn ở compile time; override chọn ở runtime**. Tuy nhiên, phải hiểu đúng phạm vi của câu này: runtime không “chọn lại overload” theo lớp thực tế của đối số; nó tìm implementation thích hợp cho chữ ký mà quá trình biên dịch đã quyết định. Phương thức `static`, `private`, constructor và các trường hợp gọi `super` có quy tắc khác với gọi phương thức instance đa hình bình thường.

Bài học này tập trung vào Java Core, đặc biệt là phân biệt **kiểu khai báo** và **kiểu thực tế**, sự phối hợp giữa overload và override trong cùng một biểu thức gọi, cùng các lỗi thường gặp khi dùng kế thừa, interface, `null`, boxing và varargs.

## 1. Phân biệt hai cơ chế

| Tiêu chí | Overload (nạp chồng) | Override (ghi đè) |
| --- | --- | --- |
| Ý tưởng | Nhiều phương thức cùng tên nhưng có danh sách tham số khác nhau | Lớp con/implementation cung cấp hành vi mới cho phương thức instance được kế thừa hoặc khai báo trong interface |
| Phân biệt phương thức | Theo tên và kiểu/số lượng/thứ tự tham số (cùng các quy tắc chữ ký của Java) | Cùng chữ ký phù hợp để override; kiểu trả về phải tương thích |
| Chọn tại đâu? | **Compile time**: kiểm tra tập phương thức khả dụng và chọn lời gọi cụ thể | **Runtime**: tìm implementation phù hợp trên lớp thực tế của receiver |
| Yếu tố quan trọng | Kiểu tĩnh của receiver và argument, cách chuyển đổi, tính đặc hiệu | Lớp runtime của receiver, quan hệ kế thừa và phương thức override |
| Ví dụ | `print(Object)` và `print(String)` | `Animal.speak()` được `Dog` override |
| Hạn chế đáng nhớ | Chỉ đổi return type không tạo overload hợp lệ | `static` là hiding; `private` không được override; không thể override `final` |

Ví dụ overload:

~~~java
void show(Object value) { }
void show(String value) { }
~~~

Ví dụ override:

~~~java
class Base {
    String name() { return "Base"; }
}

class Child extends Base {
    @Override
    String name() { return "Child"; }
}
~~~

Hai khối trên chỉ minh họa cách khai báo trong class, chưa phải hai chương trình chạy độc lập.

**Kiểu tĩnh** là kiểu Java biết lúc biên dịch, ví dụ biến `Animal pet` có kiểu tĩnh `Animal`. **Kiểu runtime** của đối tượng có thể là `Dog` nếu `pet = new Dog()`. Với overload, `pet` được xét như `Animal`; với override, phương thức instance được chọn có thể chạy phần code thuộc `Dog`.

## 2. Chương trình Java 17 hoàn chỉnh: overload và override cùng xuất hiện

Tạo tệp **OverloadOverrideDemo.java** với nội dung sau:

~~~java
public class OverloadOverrideDemo {
    static class Animal { }
    static final class Dog extends Animal { }
    static final class Cat extends Animal { }

    static class Handler {
        String handle(Animal value) {
            return "Handler.handle(Animal)";
        }

        String handle(Dog value) {
            return "Handler.handle(Dog)";
        }

        static String identify(Animal value) {
            return "Handler.identify(Animal)";
        }
    }

    static final class FastHandler extends Handler {
        @Override
        String handle(Animal value) {
            return "FastHandler.handle(Animal)";
        }

        @Override
        String handle(Dog value) {
            return "FastHandler.handle(Dog)";
        }

        // Overload MOI; khong override bat ky phuong thuc nao o Handler.
        String handle(Cat value) {
            return "FastHandler.handle(Cat)";
        }

        // Hiding static method; KHONG phai override.
        static String identify(Animal value) {
            return "FastHandler.identify(Animal)";
        }
    }

    static String choose(long value) {
        return "choose(long)";
    }

    static String choose(Integer value) {
        return "choose(Integer)";
    }

    static String choose(int... values) {
        return "choose(int...)";
    }

    static String print(Object value) {
        return "print(Object)";
    }

    static String print(String value) {
        return "print(String)";
    }

    public static void main(String[] args) {
        Handler handler = new FastHandler();
        Animal animalDog = new Dog();
        Dog dog = new Dog();
        Cat cat = new Cat();

        System.out.println("1: " + handler.handle(animalDog));
        System.out.println("2: " + handler.handle(dog));
        System.out.println("3: " + handler.handle(cat));
        System.out.println("4: "
                + ((FastHandler) handler).handle(cat));

        System.out.println("5: " + choose(7));
        Integer boxed = 7;
        System.out.println("6: " + choose(boxed));
        System.out.println("7: " + choose());

        Object text = "hello";
        System.out.println("8: " + print(text));
        System.out.println("9: " + print("hello"));
        System.out.println("10: " + print(null));

        System.out.println("11: " + Handler.identify(dog));
        System.out.println("12: " + FastHandler.identify(dog));
    }
}
~~~

Lệnh biên dịch và chạy, JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 OverloadOverrideDemo.java
java OverloadOverrideDemo
~~~

Kết quả tiêu chuẩn của chương trình:

~~~text
1: FastHandler.handle(Animal)
2: FastHandler.handle(Dog)
3: FastHandler.handle(Animal)
4: FastHandler.handle(Cat)
5: choose(long)
6: choose(Integer)
7: choose(int...)
8: print(Object)
9: print(String)
10: print(String)
11: Handler.identify(Animal)
12: FastHandler.identify(Animal)
~~~

Không có ngẫu nhiên, thread hoặc IO mạng ở ví dụ này; giá trị trả về được xác định từ các quy tắc Java nên những dòng kết quả trên có thể giải thích từng bước.

### 2.1. Vì sao dòng 1 gọi `FastHandler.handle(Animal)`?

~~~java
Handler handler = new FastHandler();
Animal animalDog = new Dog();
handler.handle(animalDog);
~~~

Ở thời điểm biên dịch:

- Receiver `handler` có kiểu tĩnh `Handler`, nên compiler xét `handle(Animal)` và `handle(Dog)` từ API của `Handler`.
- Biểu thức đối số `animalDog` có kiểu tĩnh `Animal`, dù đối tượng đang tham chiếu là `Dog`.
- `Animal` không tự động chuyển xuống `Dog`, vì thế overload được chọn là **`handle(Animal)`**.

Ở thời điểm chạy:

- Receiver thực tế là đối tượng `FastHandler`.
- `FastHandler` đã override `handle(Animal)`, vì vậy chạy **`FastHandler.handle(Animal)`**.

**Không có bước thứ ba tự nhìn đối tượng `Dog` để đổi sang `handle(Dog)`.** Đây chính là điểm cốt lõi của bài.

### 2.2. Dòng 2, 3 và 4 thay đổi điều gì?

| Lời gọi | Kiểu tĩnh receiver | Kiểu tĩnh đối số | Overload được chọn | Implementation lúc chạy |
| --- | --- | --- | --- | --- |
| `handler.handle(animalDog)` | Handler | Animal | `handle(Animal)` | `FastHandler.handle(Animal)` |
| `handler.handle(dog)` | Handler | Dog | `handle(Dog)` | `FastHandler.handle(Dog)` |
| `handler.handle(cat)` | Handler | Cat | `handle(Animal)` | `FastHandler.handle(Animal)` |
| `((FastHandler) handler).handle(cat)` | FastHandler | Cat | `handle(Cat)` | `FastHandler.handle(Cat)` |

Dòng 3 dễ gây bất ngờ: mặc dù `FastHandler` có `handle(Cat)`, biến receiver được khai báo là `Handler`. Compiler chỉ có thể xét tập method mà kiểu `Handler` cung cấp; `handle(Cat)` không thuộc tập đó, nên `Cat` được truyền lên `handle(Animal)`. Runtime chỉ dispatch override của `handle(Animal)`.

Dòng 4 dùng cast sang `FastHandler`, làm **kiểu tĩnh của biểu thức receiver đổi thành `FastHandler`**. Khi đó overload `handle(Cat)` mới trở nên khả dụng và được chọn. Cast ở đây an toàn vì đối tượng thật là `FastHandler`; với một instance `Handler` không thuộc `FastHandler`, cast như thế có thể gây `ClassCastException`. Đừng biến cast thành cách giải quyết chung cho thiết kế API.

## 3. Thứ tự suy luận một lời gọi phương thức

Có thể đọc lời gọi `receiver.method(argument)` theo quy trình:

~~~text
COMPILE TIME
  |
  +-- Kiểu tĩnh của receiver là gì?
  |
  +-- Tập phương thức có tên phù hợp, có thể truy cập là gì?
  |
  +-- Kiểu tĩnh và số lượng đối số là gì?
  |
  +-- Overload nào áp dụng được theo quy tắc chuyển đổi Java?
  |
  +-- Phương thức nào đặc hiệu nhất? Có mơ hồ không?
  |
  +-- Ghi nhận chữ ký/đích phương thức đã chọn.
  |
RUNTIME (với lời gọi phương thức instance đa hình)
  |
  +-- Đánh giá receiver, argument, kiểm tra null khi cần.
  |
  +-- Receiver thật thuộc class nào?
  |
  +-- Class đó override chữ ký đã chọn bằng method nào?
  |
  +-- Chạy implementation tương ứng.
~~~

Đoạn sơ đồ là tóm tắt phục vụ học tập. Chi tiết chuẩn hóa về tìm kiếm, khả năng truy cập, áp dụng overload và phân phối lời gọi nằm trong **Java Language Specification, mục 15.12 (Method Invocation Expressions)**. Các quy tắc cho `super`, `static`, `private`, interface, generics và method invocation kiểu đặc biệt có những chi tiết riêng; không nên hiểu sơ đồ như một thuật toán bytecode cho mọi kiểu lời gọi.

Một đối tượng runtime chỉ quyết định implementation nếu Java thực hiện dispatch instance có thể override. Với phương thức không thể override hoặc với cách gọi `super`, JVM không tự do tìm một override khác theo cách thông thường.

## 4. Compiler chọn overload dựa trên những điều gì?

Overload là nhiều khai báo cùng tên và khác nhau về **danh sách tham số**. Thứ tự tham số có ý nghĩa:

~~~java
void transfer(String from, int amount) { }
void transfer(int amount, String from) { }
~~~

Hai phương thức trên là hai overload khác nhau. Ngược lại, hai khai báo `String read(int x)` và `int read(int x)` trong cùng class là **không hợp lệ**: chỉ khác return type không đủ tạo overload.

Thêm `throws` khác hoặc đổi tên biến tham số cũng không tạo chữ ký overload mới. Đối với generic, cần chú ý **type erasure**: hai khai báo nhìn khác ở tham số generic đôi khi lại có cùng erasure nên không cùng tồn tại được.

### 4.1. Compiler xét khả năng áp dụng theo nhiều giai đoạn

Đơn giản hóa các giai đoạn Java dùng khi chọn overload:

1. **Strict invocation**: ưu tiên phương thức áp dụng được khi chưa cần boxing/unboxing hoặc lời gọi varargs theo dạng biến số; các chuyển đổi thông thường như widening primitive (`int` → `long`) và widening reference (`String` → `Object`) có thể dùng.
2. **Loose invocation**: nếu giai đoạn đầu không tìm được overload áp dụng, cho phép thêm các chuyển đổi boxing/unboxing và kết hợp được Java chấp nhận.
3. **Variable arity invocation**: nếu vẫn chưa có phương thức áp dụng, xét lời gọi varargs theo độ dài thay đổi.

Sau khi có tập ứng viên ở giai đoạn được chọn, compiler chọn phương thức **đặc hiệu nhất** theo quy tắc Java. Nếu không có lựa chọn duy nhất hợp lệ, nó báo lỗi *ambiguous method call* tại compile time. Không đúng khi nói Java luôn “chọn phương thức cần ít phép chuyển đổi nhất” theo cách đếm số lượng chuyển đổi chung chung; bộ quy tắc có giai đoạn và tiêu chí đặc hiệu riêng.

Đó là lý do ví dụ:

~~~java
choose(7);
~~~

gọi `choose(long)`: literal `7` có kiểu `int`. Chuyển `int` thành `long` bằng **widening primitive** đã áp dụng ngay ở giai đoạn strict. `choose(Integer)` cần boxing nên không được ưu tiên trước phương thức đã hợp lệ ở giai đoạn đầu. `choose(int...)` trong ví dụ là lựa chọn varargs khi không có ứng viên ở các giai đoạn trước; khi gọi `choose()`, các overload một tham số `long` và `Integer` không áp dụng được, nên chỉ còn varargs.

Với:

~~~java
Integer boxed = 7;
choose(boxed);
~~~

`Integer` khớp trực tiếp với `choose(Integer)` ở giai đoạn strict. `choose(long)` cần unboxing và widening, vì vậy dòng 6 gọi `choose(Integer)`.

**Lưu ý về varargs:** một phương thức khai báo `int...` có thể nhận một mảng `int[]` trong lời gọi kiểu fixed arity. Không thể luôn kết luận “hễ có dấu ba chấm thì chỉ được xem xét cuối cùng”. Quy tắc giai đoạn varargs nói về **variable arity invocation**; một method khai báo varargs vẫn có thể áp dụng trong giai đoạn sớm khi đối số đúng kiểu mảng.

### 4.2. Kiểu tĩnh của biến quyết định overload

Trong chương trình chính:

~~~java
Object text = "hello";
print(text);      // print(Object)
print("hello");   // print(String)
print(null);      // print(String)
~~~

Trường hợp đầu: `text` có kiểu tĩnh `Object` nên không thể truyền trực tiếp vào `print(String)`; thực tế tham chiếu tới chuỗi không thay đổi quyết định compile time. Trường hợp thứ hai: literal `"hello"` có kiểu `String`, nên `print(String)` cụ thể hơn `print(Object)`. Trường hợp cuối: literal `null` có thể truyền cho cả `Object` và `String`, nhưng `String` là subtype của `Object`, nên `print(String)` đặc hiệu hơn.

Cần cẩn thận: `null` không có một class runtime giúp “chọn phương thức”; quyết định vẫn được thực hiện lúc biên dịch.

### 4.3. Overload có thể mơ hồ ngay cả khi đều hợp lệ

Ví dụ sau cố ý **không biên dịch** nếu đặt trong cùng một class:

~~~java
static void show(String value) { }
static void show(Integer value) { }

// show(null); // Loi bien dich: ambiguous method call.
~~~

`null` tương thích với cả `String` và `Integer`, nhưng không kiểu nào là subtype của kiểu còn lại, nên không có một overload duy nhất đặc hiệu hơn.

Một trường hợp mơ hồ khác:

~~~java
static void combine(CharSequence value) { }
static void combine(java.io.Serializable value) { }

// combine("hello"); // Loi bien dich: ambiguous method call.
~~~

`String` triển khai cả `CharSequence` và `Serializable`, còn hai kiểu tham số không có quan hệ subtype để ưu tiên một overload duy nhất.

Các đoạn trong mục 4.3 chỉ để phân tích lỗi biên dịch, **không thuộc tệp OverloadOverrideDemo.java**. Nếu thực sự cần chọn một overload, có thể đưa đối số có kiểu tĩnh rõ ràng, ví dụ cast `(String) null` để chọn `show(String)`; đây là kỹ thuật làm rõ yêu cầu, không thay thế cho thiết kế API tránh overload mơ hồ.

## 5. Runtime dispatch chỉ xảy ra với override phù hợp

Lấy một ví dụ đơn giản khác: lớp con không thêm overload, chỉ override cùng chữ ký.

~~~java
class Speaker {
    String speak() {
        return "Speaker";
    }
}

class LoudSpeaker extends Speaker {
    @Override
    String speak() {
        return "LoudSpeaker";
    }
}
~~~

Đặt đoạn code trên cùng ngữ cảnh Java thích hợp rồi gọi:

~~~java
Speaker s = new LoudSpeaker();
System.out.println(s.speak()); // LoudSpeaker
~~~

Ở đây **không có overload** `speak(...)` để so sánh. Trình biên dịch nhận diện `Speaker.speak()` trong kiểu tĩnh `Speaker`. JVM gọi implementation override trong `LoudSpeaker` theo lớp runtime của `s`.

Khi gọi một phương thức override thông qua kiểu interface, nguyên lý vẫn tương tự:

~~~java
interface Reporter {
    String report();
}

class PlainReporter implements Reporter {
    @Override
    public String report() {
        return "plain";
    }
}
~~~

Ví dụ trong một phương thức:

~~~java
Reporter r = new PlainReporter();
System.out.println(r.report()); // plain
~~~

`Reporter` mô tả hợp đồng; lớp runtime `PlainReporter` cung cấp implementation. Khi một class có nhiều implementation kế thừa, Java có quy tắc lựa chọn override và default method để xác định phương thức sẽ chạy. Điều đó không làm cho overload được chọn dựa vào đối tượng runtime của argument.

## 6. `static`, `private`, `final` và `super`: các ngoại lệ cần hiểu

Không phải cứ hai method cùng tên ở cha/con là override.

| Tình huống | Cơ chế thật | Hệ quả |
| --- | --- | --- |
| Lớp con định nghĩa instance method cùng chữ ký hợp lệ như lớp cha | **Override** | Dispatch theo runtime receiver |
| Lớp con định nghĩa `static` cùng chữ ký với `static` của lớp cha | **Method hiding** | Không dispatch động theo runtime receiver |
| `private` method cùng tên/chữ ký xuất hiện ở hai lớp | Hai phương thức riêng biệt | Phương thức private của cha không bị override |
| Method `final` ở cha | Không thể override trong lớp con | Cố override gây lỗi compile time |
| `super.method()` trong lớp con | Gọi implementation của superclass được chỉ định theo ngữ nghĩa `super` | Không dispatch lại về override của chính lớp con |
| Constructor cùng tên class | Overload constructor, không override constructor | Constructor không kế thừa và không tham gia dynamic dispatch như instance method |

Dòng 11 và 12 trong chương trình hoàn chỉnh minh họa **static hiding**:

~~~java
Handler.identify(dog);      // Handler.identify(Animal)
FastHandler.identify(dog);  // FastHandler.identify(Animal)
~~~

Lớp `FastHandler` khai báo lại static `identify(Animal)`; nó **che** phương thức static của lớp cha chứ không override. Nên gọi static method bằng **tên class** như trên. Java cho phép một số dạng truy cập static qua biến instance, nhưng cách viết ấy gây hiểu nhầm rằng static method có runtime dispatch.

Trong thực tế, `private` helper thường dùng để giữ logic nội bộ, còn `final` method dùng khi muốn ngăn lớp con thay đổi hành vi của phương thức. Cả hai cần được lựa chọn theo mục đích thiết kế, chứ không chỉ để né đa hình.

## 7. Overload và override có thể phối hợp nhưng không đổi nhiệm vụ

Giả sử bạn xây một API xử lý dữ liệu:

~~~java
class ParentProcessor {
    String process(Object input) {
        return "Parent object";
    }
}

class ChildProcessor extends ParentProcessor {
    @Override
    String process(Object input) {
        return "Child object";
    }

    String process(String input) {
        return "Child string";
    }
}
~~~

Các biểu thức minh họa:

~~~java
ParentProcessor p = new ChildProcessor();
Object value = "abc";

// p.process(value) -> "Child object"
// p.process("abc") -> "Child object"
// ((ChildProcessor) p).process("abc") -> "Child string"
~~~

Ở cả hai lời gọi thông qua `p`, compiler chỉ thấy `process(Object)` của `ParentProcessor`; runtime tìm bản override `process(Object)` của `ChildProcessor`, kể cả khi đối số là chuỗi. Chỉ khi receiver tĩnh chuyển thành `ChildProcessor` thì overload `process(String)` mới là ứng viên để compiler xem xét.

Đừng thiết kế hệ thống kỳ vọng overload tự động trở thành **dispatch kép** trên cả receiver và đối số. Java thông thường dispatch một lần theo runtime receiver cho chữ ký được chọn; nó không tự so kiểu runtime của mọi argument để tìm overload phù hợp nhất.

Nếu mục tiêu nghiệp vụ là xử lý khác nhau dựa trên **kiểu runtime của argument**, các lựa chọn chủ động bao gồm:

- Gọi overload ở nơi mà kiểu tĩnh cụ thể đã được xác định.
- Dùng một hợp đồng đa hình trên chính đối tượng argument, để đối tượng đó gọi logic phù hợp (ví dụ `animal.accept(visitor)` trong mẫu Visitor khi thật sự cần nhiều phép phân phối).
- Dùng `instanceof` với pattern matching của Java khi các nhánh kiểu là hữu hạn, rõ ràng và phù hợp bối cảnh.

Không nên áp dụng một mẫu thiết kế phức tạp chỉ vì có hai overload; ưu tiên một API rõ ràng và logic dễ kiểm thử.

## 8. Overload với kế thừa, generics và type erasure

Khi có kế thừa và generic, cần nhớ thêm các quy tắc:

**Overload resolution vẫn dựa trên biểu thức ở compile time.** Nếu khai báo `List<Animal>` và đối tượng runtime thực chất được tạo từ `ArrayList<Animal>`, lời gọi vẫn dựa trên các phương thức có thể thấy qua kiểu tĩnh `List<Animal>`.

**Type erasure ảnh hưởng đến chữ ký ở JVM.** Hai phương thức cùng tên khác nhau duy nhất ở tham số generic như:

~~~java
void load(java.util.List<String> values) { }
void load(java.util.List<Integer> values) { }
~~~

không được cùng khai báo trong một class: sau erasure, cả hai đều có tham số `List`, dẫn đến **name clash**. Đây là ví dụ mã cố ý không hợp lệ; không đưa vào file runnable.

**Override với generic vẫn có thể dispatch động.** Compiler có thể tạo *bridge method* để giữ cơ chế override sau erasure và các kiểu trả về covariant. Đây là chi tiết tương thích của compiler/JVM; từ phía lập trình viên, lời gọi hợp lệ vẫn tuân theo quy tắc overload tại compile time và override tại runtime.

Ví dụ bridge method về mặt khái niệm:

~~~java
interface Converter<T> {
    T convert(T value);
}

final class UppercaseConverter implements Converter<String> {
    @Override
    public String convert(String value) {
        return value.toUpperCase(java.util.Locale.ROOT);
    }
}
~~~

Khi dùng `Converter<String> converter = new UppercaseConverter();`, lời gọi `converter.convert("java")` trả `"JAVA"`. Với generics, compiler tạo/cài đặt các cơ chế cần thiết để implementation của `UppercaseConverter` phù hợp phương thức interface sau erasure; người dùng API không cần gọi bridge method bằng tay.

Lưu ý không lẫn **override-equivalent signatures**, các quy tắc subsignature, erasure và overload. Những trường hợp tinh vi nên được đối chiếu với JLS và kiểm thử biên dịch ở phiên bản Java mục tiêu.

## 9. Những lỗi tư duy dẫn đến bug

| Nhầm lẫn | Điều Java thật sự làm | Cách kiểm tra |
| --- | --- | --- |
| “Đối tượng argument là Dog thì tự chọn overload Dog” | Overload xét kiểu **tĩnh** của biểu thức argument | Viết ra kiểu khai báo của từng biến và danh sách overload khả dụng |
| “Receiver là FastHandler nên mọi overload riêng của FastHandler đều dùng được” | Tập overload được xác định theo kiểu **tĩnh** receiver | Thử thay `Handler h` bằng `FastHandler h`, quan sát sự khác biệt |
| “Override quyết định lại kiểu tham số” | Override chọn implementation cho chữ ký đã xác định | Ghi chữ ký compile time trước rồi mới xác định lớp runtime |
| “`static` cùng tên ở lớp con là override” | Đây là method hiding | Dùng tên class khi gọi static, không kỳ vọng đa hình |
| “Chỉ đổi return type là nạp chồng” | Không tạo chữ ký overload khác | Đối chiếu tên và danh sách tham số |
| “Boxing luôn được ưu tiên hơn widening” | Quy tắc giai đoạn strict có thể chọn primitive widening trước boxing | Kiểm tra method applicability theo giai đoạn |
| “`null` luôn chọn overload có kiểu tham chiếu” | Có thể chọn subtype đặc hiệu hơn hoặc bị ambiguous | So sánh quan hệ subtype giữa các kiểu tham số |
| “Mọi phương thức có varargs đều chỉ được xem ở giai đoạn cuối” | Varargs method cũng có thể áp dụng ở dạng fixed arity khi nhận mảng thích hợp | Phân biệt kiểu tham số `T[]` với mở rộng varargs |
| “Đã có override thì gọi qua `super` vẫn chạy override của lớp con” | `super.method()` có semantics gọi bản được chọn từ superclass | Đọc loại invocation và phạm vi từ khóa `super` |

## 10. Phương pháp phân tích mọi lời gọi

Gặp mã khó đọc, hãy điền hai dòng sau trước khi dự đoán output:

~~~text
Bước 1 — COMPILE TIME:
  Kiểu tĩnh receiver: ...
  Kiểu tĩnh argument: ...
  Các overload thấy được: ...
  Overload/chữ ký được chọn: ...

Bước 2 — RUNTIME:
  Lớp thực tế receiver: ...
  Có override hợp lệ cho chữ ký ở bước 1? ...
  Implementation thực thi: ...
~~~

Áp dụng với ví dụ:

~~~java
Handler h = new FastHandler();
Animal a = new Dog();
h.handle(a);
~~~

Ta có:

~~~text
Bước 1 — COMPILE TIME:
  Receiver: Handler
  Argument: Animal
  Overloads: handle(Animal), handle(Dog)
  Chữ ký chọn: handle(Animal)

Bước 2 — RUNTIME:
  Receiver thực tế: FastHandler
  Override: FastHandler.handle(Animal)
  Kết quả: "FastHandler.handle(Animal)"
~~~

Đây là cách kiểm tra đáng tin hơn việc chỉ nhìn biểu thức `new Dog()` và đoán Java sẽ gọi phương thức gần `Dog` nhất.

## 11. Bài tập có đáp án

### Bài 1 — Kiểu khai báo khác kiểu thực tế

Giả sử trong class có hai overload `test(Object)` và `test(String)`:

~~~java
Object x = "ABC";
// test(x) sẽ chọn chữ ký nào?
~~~

**Đáp án:** `test(Object)`, vì `x` có kiểu tĩnh `Object`. Chuỗi thực tế `"ABC"` không làm compiler chọn lại `test(String)`.

### Bài 2 — Override nhưng không có overload mới

~~~java
class A {
    String label(Number x) { return "A"; }
}
class B extends A {
    @Override
    String label(Number x) { return "B"; }
}

A ref = new B();
// ref.label(Integer.valueOf(9)) trả gì?
~~~

**Đáp án:** `"B"`. Compiler chọn `label(Number)`, vì `Integer` có thể được chuyển lên `Number`. Runtime receiver là `B`, nên dùng bản override `B.label(Number)`. Đoạn khai báo `ref` và lời gọi cần đặt trong một phương thức khi dùng làm chương trình đầy đủ.

### Bài 3 — Khi overload không rõ ràng

Có hai overload `test(String)` và `test(Integer)`; gọi `test(null)` có chạy một trong hai method không?

**Đáp án:** không; compiler báo lỗi ambiguous vì không có một overload đặc hiệu hơn overload còn lại. Có thể làm rõ đích bằng `test((String) null)` nếu đó thật sự là ý định của chương trình.

### Bài 4 — Một overload ở lớp con bị “ẩn” bởi kiểu tĩnh receiver

Lấy `Handler`, `FastHandler`, `Cat` của chương trình chính. Tại sao `Handler h = new FastHandler(); h.handle(new Cat());` không gọi `FastHandler.handle(Cat)`?

**Đáp án:** kiểu tĩnh receiver là `Handler`, và `Handler` không khai báo `handle(Cat)`. Compiler chọn `handle(Animal)`, sau đó runtime tìm override `FastHandler.handle(Animal)`. Java không thực hiện overload resolution lần nữa ở runtime.

### Bài 5 — Primitive widening, boxing và varargs

Với `choose(long)`, `choose(Integer)`, `choose(int...)` như chương trình chính, hãy giải thích kết quả `choose(7)`, `choose(Integer.valueOf(7))`, `choose()`.

**Đáp án:** lần lượt chọn `long` (widening primitive áp dụng ở strict phase), `Integer` (exact reference match), `int...` (giai đoạn variable arity cho 0 đối số).

## 12. Ghi nhớ để dùng khi thiết kế API

- **Dùng overload** khi nhiều thao tác có cùng ý nghĩa nhưng nhận các dạng dữ liệu khác nhau. Tránh các cặp overload dễ mơ hồ với `null`, auto-boxing hoặc kiểu cha/con.
- **Dùng override** khi cùng một hợp đồng instance cần hành vi khác theo implementation runtime; khi đó consumer nên làm việc qua kiểu cha/interface phù hợp.
- **Đừng dựa vào runtime argument để chọn overload.** Muốn phân nhánh theo kiểu runtime của argument, cần một thiết kế kiểm soát việc phân phối rõ ràng.
- **Khi debug một lời gọi, xác định chữ ký compile time trước.** Sau đó mới tìm implementation theo runtime receiver. Với static, private hoặc `super`, áp dụng quy tắc riêng thay vì mô hình override động.
- **Đọc thông báo compile error về ambiguous overload, incompatible types, name clash.** Những lỗi này cho biết compiler không tìm được một chữ ký hợp lệ duy nhất từ thông tin kiểu tĩnh.

Điểm mấu chốt: **overload trả lời “ta đang gọi phương thức có danh sách tham số nào?”, còn override trả lời “implementation của phương thức đó trên đối tượng hiện tại là gì?”**. Tách hai câu hỏi này giúp giải thích đúng đa hình Java, kể cả khi kiểu khai báo, kiểu thực tế và các overload ở lớp cha/con khác nhau.