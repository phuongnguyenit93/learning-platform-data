# Tính đầy đủ, boxing, unboxing và null

Primitive type patterns mở rộng pattern matching của Java để làm việc với cả kiểu nguyên thủy và kiểu tham chiếu. Khi kiểm tra một giá trị bằng instanceof hoặc case, Java có thể thực hiện chuyển đổi giữa các kiểu nếu phép chuyển đổi đó an toàn và không làm mất thông tin. Boxing, unboxing, kiểm tra tính chính xác của phép chuyển đổi và xử lý null quyết định một giá trị có khớp pattern hay không.

Trong JDK 26, tính năng này thuộc JEP 530 – Primitive Types in Patterns, instanceof, and switch (Fourth Preview). Tại thời điểm 27/11/2026, JDK 27 đã phát hành GA nhưng tính năng vẫn là preview lần thứ năm theo JEP 532. Vì vậy, nội dung dưới đây mô tả cách dùng trong JDK 26 và nêu rõ các điều kiện vẫn cần kiểm tra khi chuyển sang JDK 27. Đây chưa phải tính năng ngôn ngữ chính thức.

## 1. Phạm vi tính năng và cách bật preview

Java 26 cho phép dùng kiểu nguyên thủy trong các pattern, trong instanceof và trong selector của switch. Những kiểu được hỗ trợ gồm:

- Kiểu số nguyên: byte, short, char, int, long.
- Kiểu dấu phẩy động: float, double.
- Kiểu logic: boolean.

Có thể dùng primitive type pattern ở cấp cao nhất và bên trong record pattern. instanceof có thể kiểm tra phép chuyển đổi giữa kiểu nguyên thủy và kiểu tham chiếu, cũng như giữa hai kiểu nguyên thủy. switch có thể nhận các kiểu nguyên thủy mới như long, float, double, boolean và các wrapper tương ứng.

Phân biệt trạng thái:

| Môi trường | JEP | Trạng thái |
|---|---|---|
| JDK 26 | JEP 530 | Preview lần thứ tư |
| JDK 27 | JEP 532 | Preview lần thứ năm, vẫn là preview tại thời điểm viết bài |

Biên dịch và chạy ví dụ preview bằng cùng một phiên bản JDK. Với JDK 26:

~~~powershell
javac --enable-preview --release 26 -d out src\Main.java
java --enable-preview -cp out Main
~~~

Nếu chuyển sang JDK 27, phải dùng compiler và runtime của JDK 27, đồng thời đổi release thành 27:

~~~powershell
javac --enable-preview --release 27 -d out src\Main.java
java --enable-preview -cp out Main
~~~

Không thể dùng JDK 27 với --release 26 để bật preview Java 26. Cờ preview gắn với chính phiên bản JDK đang chạy compiler và runtime. Các pattern trên kiểu tham chiếu vốn đã được chuẩn hóa vẫn là ngôn ngữ Java thông thường; phần mở rộng cho kiểu nguyên thủy trong bài này cần cờ preview.

## 2. Pattern chỉ khớp khi phép chuyển đổi chính xác

Một pattern có kiểu đích không nhất thiết yêu cầu kiểu nguồn phải giống hệt kiểu đích. Java xét một testing conversion từ kiểu nguồn sang kiểu trong pattern. Phép chuyển đổi được xem là chính xác (exact) nếu nó không làm mất thông tin và không gây exception. Nếu phép chuyển đổi không chính xác, pattern không khớp.

Điểm này khác với phép ép kiểu thông thường. Ép kiểu số có thể cắt phần thập phân, tràn phạm vi hoặc làm mất độ chính xác mà không ném exception. Pattern matching chỉ thành công nếu giá trị có thể chuyển đổi mà vẫn giữ nguyên thông tin.

Ví dụ:

~~~java
static void inspect(float value) {
    if (value instanceof float f) {
        System.out.println("float: " + f);
    }

    if (value instanceof double d) {
        System.out.println("double: " + d);
    }

    if (value instanceof int i) {
        System.out.println("int chính xác: " + i);
    }
}
~~~

Với value = 1000.01f, pattern float f khớp vì kiểu giống nhau. Pattern double d cũng khớp vì mọi giá trị float đều biểu diễn chính xác được bằng double. Pattern int i không khớp vì chuyển 1000.01f thành 1000 sẽ làm mất phần thập phân.

Với value = 1000.0f, pattern int i có thể khớp vì giá trị sau chuyển đổi vẫn là 1000. Việc một phép chuyển đổi số có thể mất thông tin nói chung không có nghĩa mọi giá trị đều thất bại; Java xét giá trị thực tế ở thời điểm chạy.

### Ví dụ kiểm tra phạm vi trước khi lấy kiểu hẹp hơn

~~~java
static void inspectInt(int value) {
    if (value instanceof byte small) {
        // Chỉ chạy nếu value nằm trong phạm vi byte.
        System.out.println("byte: " + small);
    } else {
        System.out.println("Không thể chuyển sang byte mà giữ nguyên giá trị");
    }
}
~~~

value = 42 khớp với byte small. value = 234 không khớp vì giá trị 234 không thể biểu diễn bằng byte mà không đổi giá trị. Pattern vừa kiểm tra điều kiện vừa cung cấp biến small đã có kiểu byte.

Không dùng phép ép kiểu (byte) value để thay thế phép kiểm tra này nếu yêu cầu là giữ nguyên giá trị. Ép kiểu có thể biến 234 thành một giá trị byte khác; pattern chỉ thành công khi phép chuyển đổi là chính xác.

## 3. Boxing: từ giá trị nguyên thủy sang pattern kiểu tham chiếu

Boxing chuyển một giá trị nguyên thủy thành đối tượng wrapper tương ứng. Trong testing context của pattern matching, Java có thể boxing rồi thực hiện widening reference conversion để khớp với kiểu tham chiếu rộng hơn.

~~~java
static void inspectPrimitive(int value) {
    if (value instanceof Integer boxed) {
        System.out.println("Integer: " + boxed);
    }

    if (value instanceof Number number) {
        System.out.println("Number: " + number);
    }

    if (value instanceof Object object) {
        System.out.println("Object: " + object);
    }
}
~~~

Với value = 42, cả ba pattern đều khớp:

1. int được boxing thành Integer, nên pattern Integer boxed khớp.
2. Giá trị đã boxing có thể widening reference conversion từ Integer sang Number.
3. Giá trị đã boxing cũng có thể widening reference conversion sang Object.

Biến pattern có kiểu tham chiếu đã khai báo. Ví dụ boxed có kiểu Integer, còn number có kiểu Number. Đây là chuyển đổi trong quá trình kiểm tra pattern; không có nghĩa biến nguồn value bị đổi kiểu hoặc bị thay thế.

Boxing trong pattern matching cũng có thể phát sinh chi phí tạo hoặc lấy wrapper object. Không nên dùng pattern để boxing lặp lại trong vòng lặp hiệu năng cao nếu không cần thiết. Hãy đo hiệu năng trên workload thật và để JVM tối ưu các trường hợp phù hợp.

## 4. Unboxing: từ wrapper hoặc reference sang kiểu nguyên thủy

Unboxing lấy giá trị nguyên thủy bên trong wrapper. Sau unboxing, testing conversion có thể tiếp tục bằng widening primitive conversion nếu phép chuyển đổi đó được cho phép.

~~~java
static void inspectWrapper(Integer boxed) {
    if (boxed instanceof int value) {
        System.out.println("int: " + value);
    }

    if (boxed instanceof long wider) {
        System.out.println("long: " + wider);
    }

    if (boxed instanceof double decimal) {
        System.out.println("double: " + decimal);
    }
}
~~~

Nếu boxed là Integer.valueOf(42), cả ba pattern đều khớp:

- Integer được unbox thành int.
- int được widening chính xác thành long.
- int được widening chính xác thành double.

Biến pattern nhận giá trị đã chuyển đổi và có kiểu đúng với pattern. Ví dụ wider có kiểu long, không phải Integer.

### Kiểu nguồn tĩnh vẫn quan trọng

Nếu giá trị có kiểu tĩnh Object, pattern primitive có thể cần kiểm tra narrowing reference conversion đến wrapper tương ứng, sau đó unbox:

~~~java
static void inspectObject(Object value) {
    if (value instanceof int number) {
        System.out.println("Giá trị Integer: " + number);
    }
}
~~~

Khi value tham chiếu đến Integer.valueOf(42), pattern khớp. Nếu nó tham chiếu đến Long.valueOf(42L), pattern int number không khớp: phép kiểm tra từ Object đến int không gọi Number.intValue() và không tự chọn một wrapper bất kỳ để đổi số.

Không được suy luận rằng mọi wrapper số đều có thể unbox rồi chuyển sang mọi primitive. Testing context của kiểu tham chiếu chỉ cho phép những chuỗi chuyển đổi được đặc tả, chẳng hạn unboxing rồi widening primitive conversion. Một phép narrowing primitive conversion sau unboxing không tự động được thêm vào. Hãy xét kiểu nguồn tĩnh và loại wrapper thực tế trước khi chọn pattern.

### So sánh instanceof kiểu đích và instanceof pattern

Hai dạng dưới đây có mục đích khác nhau:

~~~java
int value = 100;

if (value instanceof byte) {
    // Chỉ kiểm tra phép chuyển đổi sang byte có chính xác hay không.
    byte converted = (byte) value;
    System.out.println(converted);
}

if (value instanceof byte small) {
    // Kiểm tra và đồng thời tạo biến pattern kiểu byte.
    System.out.println(small);
}
~~~

value instanceof byte là type comparison: biểu thức trả về boolean, không tạo biến và không trả về giá trị đã chuyển đổi. value instanceof byte small là pattern matching: nếu kiểm tra thành công, biến small được khởi tạo với giá trị kiểu byte.

Cả hai đều dùng quy tắc testing conversion. Chúng không cho phép ép kiểu mất thông tin rồi xem kết quả đó là an toàn.

## 5. Tính đầy đủ và phép chuyển đổi luôn chính xác

Một pattern có thể được xem là bao phủ toàn bộ một kiểu nếu mọi giá trị thuộc kiểu đó đều khớp. Trong đặc tả Java, khái niệm liên quan là pattern unconditional for a type và phép chuyển đổi unconditionally exact. Compiler dùng các khái niệm này khi kiểm tra tính đầy đủ của switch và phát hiện pattern bị pattern trước đó chi phối.

Một số phép chuyển đổi luôn chính xác theo kiểu:

- Identity conversion: từ một kiểu sang chính kiểu đó.
- Exact widening primitive conversion: ví dụ float sang double, hoặc int sang long.
- Widening reference conversion: ví dụ Integer sang Number.
- Boxing conversion và boxing rồi widening reference conversion.

Không phải mọi widening primitive conversion đều luôn chính xác. Chuyển int sang float có thể mất các bit có nghĩa; chuyển long sang double cũng có thể mất độ chính xác. Chuyển float sang double luôn giữ nguyên giá trị.

Ví dụ switch đầy đủ vì mọi giá trị float đều chuyển chính xác sang double:

~~~java
static String describe(float value) {
    return switch (value) {
        case double d -> "Giá trị double: " + d;
    };
}
~~~

Ngược lại, float sang int có thể làm mất phần thập phân hoặc phạm vi. Vì thế, pattern case int i không bao phủ mọi giá trị float; cần có nhánh xử lý các giá trị không khớp:

~~~java
static String describeAsInt(float value) {
    return switch (value) {
        case int i -> "Số nguyên chính xác: " + i;
        default -> "Không thể chuyển sang int mà giữ nguyên giá trị";
    };
}
~~~

Tương tự, một pattern case float f không bao phủ mọi giá trị int, vì có những giá trị int không thể biểu diễn chính xác bằng float. Đừng coi một phép widening là luôn chính xác chỉ dựa trên tên gọi widening.

### Hằng số có thể được kiểm tra chính xác ngay lúc biên dịch

Đặc tả còn có khái niệm value-based unconditionally exact conversion. Một số phép chuyển đổi có thể mất thông tin với giá trị bất kỳ, nhưng nếu nguồn là constant expression và compiler chứng minh được giá trị cụ thể chuyển đổi chính xác, phép chuyển đổi đó có thể được xem là unconditionally exact cho hằng số ấy.

Ví dụ, 42 có thể chuyển từ int sang byte chính xác. Nhưng điều đó không có nghĩa mọi giá trị int đều chuyển chính xác sang byte. Khác biệt này ảnh hưởng đến việc compiler phát hiện một nhãn case không thể được chạy vì đã bị pattern trước đó bao phủ.

~~~java
static String classify(int value) {
    return switch (value) {
        case float f -> "Khớp pattern float: " + f;
        default -> "Không thể chuyển chính xác sang float";
    };
}
~~~

Trong switch trên, những giá trị int có thể biểu diễn chính xác bằng float sẽ khớp pattern. Các giá trị khác đi vào default. Nếu thêm một nhãn hằng số đã được pattern đứng trước bao phủ, compiler có thể báo lỗi dominance vì nhánh đó không thể được chọn.

Không sửa lỗi dominance bằng cách đảo thứ tự các nhãn một cách máy móc. Hãy kiểm tra xem pattern trước có thật sự bao phủ giá trị của nhãn sau hay không; nếu có, loại bỏ nhánh thừa hoặc viết lại điều kiện để thể hiện rõ miền giá trị mong muốn.

## 6. Wrapper, tính đầy đủ của switch và null

Wrapper là kiểu tham chiếu nên có thể chứa null. Primitive thì không có giá trị null. Đây là khác biệt quan trọng khi compiler xác định một switch có đầy đủ hay không.

Ví dụ sau dùng selector Integer và primitive pattern double:

~~~java
static String describe(Integer value) {
    return switch (value) {
        case null -> "Không có giá trị";
        case double number -> "Giá trị: " + number;
    };
}
~~~

Đối với một Integer khác null, Java unbox thành int rồi widening chính xác sang double. Do đó, pattern double number bao phủ mọi giá trị không-null của Integer. Nhánh case null xử lý trường hợp còn lại.

Đặc tả có một quy tắc riêng cho exhaustiveness: một wrapper selector có thể được xem là được bao phủ bởi primitive type pattern khi chuyển đổi từ primitive tương ứng của wrapper sang kiểu primitive trong pattern là type-based unconditionally exact. Ví dụ, Integer có thể được bao phủ bởi case double number vì int sang double luôn chính xác.

Tuy nhiên, null không thuộc miền giá trị của kiểu primitive. Một switch có thể được compiler xem là exhaustive theo miền primitive nhưng vẫn gặp MatchException nếu selector wrapper thực tế là null. Vì vậy, khi selector có kiểu tham chiếu, hãy xử lý null tường minh bằng case null nếu null là đầu vào hợp lệ.

### default và case null có vai trò khác nhau

default xử lý các giá trị không khớp nhãn khác trong miền switch; nó không thay thế rõ ràng cho nhánh case null của selector tham chiếu. Với dữ liệu có thể null, hãy thiết kế nhánh null ngay trong switch:

~~~java
static String render(Integer value) {
    return switch (value) {
        case null -> "(trống)";
        case int number when number >= 0 -> "Không âm: " + number;
        case int number -> "Âm: " + number;
    };
}
~~~

Ở đây case int number unbox giá trị Integer và khởi tạo biến primitive. when kiểm tra điều kiện bổ sung trên biến pattern đã có kiểu int. Vì nhánh null được xử lý riêng, guard không phải thực hiện unboxing trên một giá trị null.

Không dùng case null cho selector primitive. Một biến int, long, float hoặc boolean không thể chứa null. Nếu một giá trị có thể thiếu, kiểu nguồn của nó thường là wrapper hoặc một kiểu tham chiếu khác.

## 7. Null trong instanceof và record pattern

### Pattern ở cấp cao nhất không khớp null

Với instanceof, giá trị null không khớp pattern kiểu tham chiếu hoặc primitive:

~~~java
Integer missing = null;

System.out.println(missing instanceof Integer value); // false
System.out.println(missing instanceof int value);     // false
System.out.println(missing instanceof Number value);  // false
~~~

Điều này khác với unboxing tường minh:

~~~java
Integer missing = null;
int value = missing; // NullPointerException
~~~

Trong pattern matching, Java kiểm tra null trước khi thực hiện chuyển đổi cần unbox. Nếu nguồn là null, pattern không khớp; không phát sinh NullPointerException chỉ vì pattern có kiểu primitive.

Nếu pattern không khớp, biến pattern không được khởi tạo và chỉ có thể được dùng trong nhánh mà quy tắc flow scoping cho phép. Không cố truy cập biến pattern ở ngoài nhánh kiểm tra thành công.

### Record pattern có quy tắc null-matching riêng cho component

Một record pattern ở cấp cao nhất không khớp nếu chính record reference là null. Tuy nhiên, type pattern nằm trực tiếp trong danh sách component của record pattern có thể khớp với null component nếu pattern đó là unconditional cho kiểu tham chiếu tĩnh của component.

~~~java
record Reading(Integer value) { }

static void inspectReading(Reading reading) {
    if (reading instanceof Reading(Integer value)) {
        // Pattern Integer là unconditional cho component kiểu Integer.
        // Nếu component null, biến value cũng được khởi tạo bằng null.
        System.out.println(value == null ? "Component null" : value);
    }

    if (reading instanceof Reading(int value)) {
        // Primitive pattern cần unbox; component null không khớp.
        System.out.println("Primitive value: " + value);
    }
}
~~~

Hai phép kiểm tra có kết quả khác nhau khi reading là new Reading(null):

- Reading(Integer value) khớp vì type pattern tham chiếu Integer là unconditional cho component có kiểu tĩnh Integer; đây là trường hợp null-matching của nested type pattern.
- Reading(int value) không khớp vì không thể unbox null. Pattern thất bại bình thường và không ném NullPointerException.

Nếu chính biến reading là null, cả hai record pattern đều không khớp. Quy tắc null-matching ở trên chỉ áp dụng cho component nằm bên trong một record instance hợp lệ.

Không suy rộng quy tắc này cho mọi nested pattern. Một pattern tham chiếu chỉ null-matching khi nó là unconditional cho kiểu tĩnh của component tương ứng. Nếu pattern cần kiểm tra kiểu hoặc chuyển đổi có thể thất bại, null không tự động được chấp nhận.

## 8. Bảng quyết định nhanh

| Kiểu nguồn | Pattern đích | Cách chuyển đổi | Khi nào khớp |
|---|---|---|---|
| int | Integer i | Boxing | Luôn khớp với giá trị int hợp lệ |
| int | Number n | Boxing rồi widening reference | Luôn khớp với giá trị int hợp lệ |
| Integer khác null | int i | Unboxing | Khớp; lấy giá trị nguyên thủy |
| Integer khác null | long l | Unboxing rồi widening | Khớp; chuyển int sang long chính xác |
| Integer null | int i | Không thực hiện unboxing | Không khớp |
| float | double d | Widening primitive chính xác | Luôn khớp |
| float | int i | Narrowing primitive | Chỉ khớp nếu không mất thông tin |
| int | byte b | Narrowing primitive | Chỉ khớp nếu giá trị nằm trong miền byte |
| int | float f | Widening primitive có thể mất độ chính xác | Chỉ khớp nếu giá trị cụ thể biểu diễn chính xác |
| Object chứa Integer | int i | Checked narrowing reference đến Integer, rồi unboxing | Khớp nếu đối tượng thực sự là Integer và không null |
| Object chứa Long | int i | Không có chuyển đổi testing hợp lệ từ Object sang int qua Long | Không khớp |

Bảng này mô tả những trường hợp điển hình. Với một biểu thức phức tạp, hãy xác định kiểu tĩnh của biểu thức trước, sau đó xét chuỗi testing conversion mà JLS cho phép.

## 9. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Compiler báo preview feature bị tắt | Chưa bật preview khi biên dịch | Dùng --enable-preview và --release cùng phiên bản JDK |
| Runtime báo preview feature không được bật | Chỉ bật preview ở compiler | Thêm --enable-preview khi chạy |
| Pattern primitive không khớp dù có thể ép kiểu | Phép ép kiểu thông thường làm mất thông tin | Dùng pattern matching và kiểm tra điều kiện exactness |
| Integer null không khớp int pattern | Unboxing không thể thực hiện với null | Kiểm tra null hoặc thêm case null trong switch |
| Switch wrapper được compiler xem là exhaustive nhưng gặp MatchException | Exhaustiveness theo primitive pattern không bao gồm null | Thêm nhánh case null |
| Long không khớp pattern int | Unboxing long rồi narrowing sang int không phải testing conversion được cho phép cho nguồn tham chiếu | Dùng pattern phù hợp với kiểu nguồn, hoặc chuyển đổi và kiểm tra rõ ràng ở tầng nghiệp vụ |
| Nhãn case bị báo dominated | Pattern trước đã bao phủ giá trị của pattern hoặc hằng số sau | Xem lại tính unconditional, exactness và thứ tự nhãn |
| Record pattern không khớp khi component null | Nested pattern không phải null-matching cho kiểu component | Chọn pattern tham chiếu unconditional nếu muốn giữ null, hoặc xử lý null riêng |

## 10. Bài thực hành kiểm chứng

Tạo một lớp Java 26 có thể biên dịch và chạy với preview. Ghi lại kết quả từng phép kiểm tra để phân biệt kết quả false, lỗi biên dịch và exception.

1. Khai báo một biến int có giá trị 42; thử pattern Integer, Number và Object. Giải thích boxing và widening reference conversion.
2. Khai báo một Integer có giá trị 42; thử pattern int, long và double. Xác định bước unboxing và widening.
3. Đổi Integer thành null. Xác nhận instanceof int i trả về false, sau đó so sánh với phép gán int n = boxed để thấy khác biệt về null.
4. Khai báo Object tham chiếu đến một Integer, rồi một Long. Thử instanceof int i và giải thích vai trò của kiểu wrapper thực tế.
5. Dùng một float có phần thập phân và một float biểu diễn số nguyên chính xác. Thử pattern int i; ghi rõ khi nào chuyển đổi là exact.
6. Dùng int nằm trong và ngoài miền byte. Thử instanceof byte b và so sánh với ép kiểu (byte) value.
7. Viết switch nhận float, dùng case double d và giải thích vì sao pattern bao phủ toàn bộ selector.
8. Viết switch nhận float với case int i và default. Kiểm tra các giá trị nguyên chính xác, số có phần thập phân, vô cực và NaN.
9. Viết switch nhận Integer với case null và case double d. Bỏ nhánh null trong một bản thử riêng và quan sát hành vi khi selector là null.
10. Tạo record Reading(Integer value). So sánh Reading(Integer value) và Reading(int value) khi component là số nguyên, null và khi record reference là null.
11. Thử một switch có pattern bao phủ một hằng số cụ thể đứng sau nó. Đọc thông báo dominance của compiler và giải thích vì sao nhãn sau không thể được chọn.
12. Biên dịch và chạy bằng JDK 26 với cờ preview. Nếu kiểm tra JDK 27, dùng preview của chính JDK 27 và ghi rõ release tương ứng.

**Tiêu chí hoàn thành:** giải thích được testing conversion và exactness; phân biệt boxing với unboxing; biết pattern primitive có thể nhận giá trị từ wrapper nhưng null không được unbox; phân biệt instanceof type comparison với pattern matching; giải thích được pattern unconditional, switch exhaustiveness và dominance; xử lý đúng null ở switch và nested record pattern.

## 11. Tài liệu tham khảo chính thức

- [JEP 530: Primitive Types in Patterns, instanceof, and switch (Fourth Preview)](https://openjdk.org/jeps/530) — phạm vi thay đổi trong JDK 26.
- [Java 26 JLS: Primitive Types in Patterns, instanceof, and switch](https://docs.oracle.com/en/java/javase/26/docs/specs/primitive-types-in-patterns-instanceof-switch-jls.html) — testing conversions, exactness, pattern matching, null-matching, dominance và exhaustiveness.
- [Java 26: Type Patterns](https://docs.oracle.com/en/java/javase/26/language/type-patterns.html) — ví dụ primitive type patterns và boxing/unboxing trong pattern matching.
- [Java 26: Safe Casting with instanceof and switch](https://docs.oracle.com/en/java/javase/26/language/safe-casting-instanceof-switch.html) — kiểm tra chuyển đổi an toàn giữa các kiểu.
- [Java 26: Record Patterns](https://docs.oracle.com/en/java/javase/26/language/record-patterns.html) — pattern matching trên record component và primitive component patterns.
- [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html) — trạng thái JEP 532, preview lần thứ năm trong JDK 27.
- [Java 27 Language Changes by Release](https://docs.oracle.com/en/java/javase/27/language/java-language-changes-release.html) — trạng thái ngôn ngữ theo release.

JLS là nguồn chuẩn để xác định một phép chuyển đổi có hợp lệ hay chính xác. Tài liệu hướng dẫn giúp đọc ví dụ, còn release notes xác nhận trạng thái preview của từng JDK. Khi nâng cấp, hãy kiểm tra lại JEP và JLS của đúng phiên bản thay vì giả định preview đã trở thành tính năng chính thức.

