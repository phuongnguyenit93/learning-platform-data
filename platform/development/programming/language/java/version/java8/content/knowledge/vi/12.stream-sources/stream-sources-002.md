# Stream.of, Stream.empty và Stream.builder trong Java

## Mục tiêu học tập

Một chương trình Java không nhất thiết phải có sẵn **List** hay **Set** mới tạo được Stream. Java 8 cung cấp những cách tạo **Stream từ các giá trị trực tiếp**, phổ biến nhất là:

- **Stream.of(...)**: tạo Stream từ một giá trị hoặc một tập giá trị đã có.
- **Stream.empty()**: tạo Stream không có phần tử nào.
- **Stream.builder()**: tích lũy tuần tự các giá trị rồi tạo Stream từ một builder.

Ba cách này vẫn sử dụng bình thường trong Java hiện đại, gồm JDK 17+ và các bản mới hơn. Chúng cùng trả về Stream nhưng phù hợp những nhu cầu khác nhau: giá trị cố định, trường hợp không có dữ liệu, hay tập phần tử được quyết định dần bởi điều kiện nghiệp vụ.

Sau bài học, bạn sẽ hiểu:

1. Cách chọn **of**, **empty** hay **builder** theo tình huống thực tế.
2. Kiểu generic **Stream<T>**, cơ chế suy luận kiểu và những trường hợp cần viết rõ tham số kiểu.
3. Khác biệt giữa **Stream.of(một mảng)**, **Arrays.stream(mảng)** và Stream chứa chính đối tượng mảng.
4. Vì sao **Stream.of(null)** là một trường hợp dễ gây nhầm; cách phân biệt Stream chứa null với Stream rỗng.
5. Cách sử dụng **Stream.Builder<T>.accept(...)**, **add(...)**, **build()**, cùng giới hạn vòng đời của builder.
6. Tính **lazy**, **intermediate operations**, **terminal operations** và quy tắc Stream **chỉ dùng một lần**.
7. Những cách viết mã an toàn, gọn, rõ kiểu và dễ kiểm thử.

Các chương trình độc lập có tên tệp, lệnh **javac**/**java**, và stdout cụ thể. Chúng chỉ dùng các API Java 8-compatible; những API được bổ sung sau Java 8 được ghi rõ để bạn không vô tình dùng chúng khi phải biên dịch bằng JDK 8.

---

## 1. Tư duy nền tảng: nguồn Stream không phải Collection

**Stream<T>** biểu diễn một pipeline xử lý các phần tử kiểu T. Stream có thể được tạo từ Collection, mảng, generator, I/O hoặc từ những giá trị được cung cấp trực tiếp.

Ví dụ tạo từ List:

~~~java
List<String> names = Arrays.asList("An", "Binh", "Chi");
Stream<String> stream = names.stream();
~~~

Còn tạo từ các giá trị:

~~~java
Stream<String> stream = Stream.of("An", "Binh", "Chi");
~~~

Đây đều là các đoạn **minh họa** cần import các kiểu tương ứng và đặt trong method. Hai đoạn trông giống nhau khi tiêu thụ một lượt, nhưng mô hình nguồn không hoàn toàn giống nhau:

- Ở đoạn thứ nhất, đối tượng List có thể được giữ và dùng để tạo Stream mới bằng **names.stream()**.
- Ở đoạn thứ hai, lời gọi **Stream.of(...)** tạo ngay một Stream cho các giá trị được truyền vào. Muốn xử lý lại, hãy gọi **Stream.of(...)** mới hoặc giữ nguồn có khả năng sử dụng lại.
- Cả hai Stream đều chỉ được vận hành một lần theo hợp đồng Stream API.
- Intermediate operations như **filter** và **map** thường tạo pipeline lazy; terminal operations như **count**, **collect**, **findFirst** sẽ tiêu thụ pipeline.

Không nên coi Stream là một Collection có thể gọi lại **iterator()** hay terminal operation tùy ý sau khi đã tiêu thụ.

### Minh họa dòng xử lý

~~~text
"An", "Binh", "Chi"
       |
       | Stream.of(...)
       v
   Stream<String>
       |
       | filter(s -> s.length() >= 3)
       v
     pipeline
       |
       | map(String::toUpperCase)
       v
     pipeline
       |
       | collect(Collectors.toList())
       v
   [BINH, CHI]
~~~

Phương thức **Stream.of(...)** cung cấp một nguồn hữu hạn cho pipeline. Sau khi collect hoàn thành, bạn có **List kết quả**, nhưng không được chạy terminal operation mới trên chính Stream đã tiêu thụ.

## 2. Stream.of(T): một phần tử

Một overload quan trọng:

~~~java
public static <T> Stream<T> of(T t)
~~~

Đây là chữ ký API để tham khảo, không phải method bạn cần tự viết. **of(T t)** tạo một sequential Stream chứa **đúng một phần tử** t.

Ví dụ:

~~~java
Stream<String> one = Stream.of("Java");

long count = Stream.of("Java").count(); // 1
~~~

Nếu truyền một đối tượng có nhiều field hoặc một Collection vào overload một phần tử, Stream ấy vẫn có **một phần tử là đối tượng được truyền**, không tự chia nhỏ đối tượng:

~~~java
List<String> values = Arrays.asList("A", "B");

Stream<List<String>> oneList = Stream.of(values);

System.out.println(oneList.count()); // 1
~~~

Đây là đoạn minh họa. **Stream.of(values)** không tương đương **values.stream()**:

- **Stream.of(values)** có phần tử kiểu **List<String>**, số phần tử 1.
- **values.stream()** có phần tử kiểu **String**, số phần tử 2.

Khi học Stream, hãy luôn hỏi: **T của Stream<T> là gì?** Nếu T là List<String>, mỗi phần tử Stream chính là một List; nếu T là String, mỗi phần tử là một chuỗi.

## 3. Stream.of(T... values): nhiều phần tử

Overload còn lại:

~~~java
public static <T> Stream<T> of(T... values)
~~~

**Varargs** cho phép truyền các phần tử liệt kê trực tiếp:

~~~java
Stream<String> words = Stream.of("Java", "Stream", "API");

Stream<Integer> numbers = Stream.of(2, 4, 6, 8);
~~~

Những lời gọi này tạo sequential Stream với encounter order tương ứng thứ tự các giá trị đầu vào.

Ví dụ đếm số chuỗi:

~~~java
long count = Stream.of("A", "B", "C").count(); // 3
~~~

Ví dụ lọc và chuyển đổi:

~~~java
List<String> result = Stream.of("java", "api", "stream")
    .filter(word -> word.length() >= 4)
    .map(String::toUpperCase)
    .collect(Collectors.toList());
~~~

Kết quả **[JAVA, STREAM]**. Đây là đoạn minh họa; cần import List, Stream và Collectors.

**Tại sao Integer chứ không phải int?** Java generic type argument phải là reference type. Với **Stream.of(2,4,6)**, các giá trị int được boxing thành Integer để dùng trong Stream<Integer>. Nếu xử lý nhiều số nguyên thủy, hãy cân nhắc **IntStream.of(2,4,6)** để tránh các chi phí boxing không cần thiết.

### Stream.of() không có tham số

Vì overload varargs có thể nhận **không đối số**, lời gọi này hợp lệ:

~~~java
Stream<String> none = Stream.of();
~~~

Trong ngữ cảnh khai báo Stream<String>, trình biên dịch suy luận T phù hợp String. Nó là một Stream rỗng về mặt nội dung, tương đương mục tiêu sử dụng của **Stream.empty()**. Nhưng khi chủ đích là “không có phần tử”, **Stream.empty()** thường rõ nghĩa hơn.

## 4. Stream.empty(): biểu diễn không có phần tử

Chữ ký:

~~~java
public static <T> Stream<T> empty()
~~~

Nó trả một sequential Stream không chứa phần tử nào. Đây vẫn là một **đối tượng Stream hợp lệ**, không phải null.

~~~java
Stream<String> missing = Stream.empty();

long count = Stream.<String>empty().count(); // 0
~~~

Có thể dùng Stream.empty() trong một nhánh trả kết quả:

~~~java
static Stream<String> tokens(boolean enabled) {
    if (!enabled) {
        return Stream.empty();
    }
    return Stream.of("A", "B");
}
~~~

Đây là phương thức minh họa cần đặt trong lớp. Cả hai nhánh trả **Stream<String>** hợp lệ, giúp caller dùng một pipeline thống nhất:

~~~java
long count = tokens(false).count(); // 0
~~~

Không cần trả null cho “không có phần tử”. Nếu trả null, caller phải tự kiểm tra trước khi gọi filter, count hoặc collect; nếu quên có thể bị NullPointerException.

### empty không đồng nghĩa Optional.empty()

**Stream.empty()** là một Stream có **0 phần tử**. **Optional.empty()** biểu diễn một Optional không chứa giá trị. Hai API thuộc những abstraction khác nhau:

- Stream dùng cho **pipeline nhiều phần tử**, kể cả 0 phần tử.
- Optional dùng cho **giá trị có thể có hoặc không**, không phải cách thay thế tổng quát cho Collection.

Java 8 có Optional và Stream, nhưng **Optional.stream()** chỉ được bổ sung ở Java 9. Nếu viết chương trình nhắm JDK 8, không gọi Optional.stream().

## 5. Generic type inference với of và empty

Với Stream.of(...), Java suy luận T từ các đối số và ngữ cảnh kiểu đích:

~~~java
Stream<String> letters = Stream.of("A", "B");
Stream<Number> values = Stream.of(1, 2.5);
Stream<String> nothing = Stream.empty();
~~~

Các biểu thức trên là những ví dụ về việc Java tìm type argument phù hợp theo ngữ cảnh. Khi bạn đã biết rõ kiểu mong muốn, khai báo biến tường minh giúp người đọc và compiler.

Nếu cần, bạn có thể dùng **type witness**:

~~~java
Stream.<String>empty();

Stream.<Number>of(1, 2.5);
~~~

Đây là các expression minh họa. **Stream.<String>empty()** làm rõ rằng phần tử Stream thuộc String, dù không có giá trị nào để suy luận từ đối số.

### Ví dụ lồng trong method generic

~~~java
static <T> Stream<T> zeroOrOne(T item, boolean included) {
    return included ? Stream.of(item) : Stream.empty();
}
~~~

Phương thức minh họa này trả Stream<T>. Kiểu generic T xuất hiện ở cả nhánh of và empty, nên caller có thể nhận một Stream với kiểu phần tử phù hợp.

Nếu dùng kết quả trong pipeline lớn, ưu tiên giữ type information thay vì ép sang raw Stream hoặc Stream<Object> quá sớm. Raw type làm giảm type safety, gây unchecked warnings và khiến nhiều lỗi bị phát hiện muộn.

## 6. Chương trình hoàn chỉnh: of và empty

Tạo tệp **StreamOfAndEmptyDemo.java**:

~~~java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class StreamOfAndEmptyDemo {

    static Stream<String> tokens(boolean enabled) {
        return enabled
            ? Stream.of("Java", "API", "Stream")
            : Stream.empty();
    }

    public static void main(String[] args) {
        List<String> longNames = Stream.of(
                "An", "Binh", "Chi")
            .filter(name -> name.length() >= 3)
            .map(String::toUpperCase)
            .collect(Collectors.toList());

        System.out.println("Filtered: " + longNames);
        System.out.println("Single: " + Stream.of("one").count());
        System.out.println("Empty: " + Stream.<String>empty().count());
        System.out.println("Disabled: " + tokens(false).count());
        System.out.println("Enabled: " + tokens(true).count());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 StreamOfAndEmptyDemo.java
java StreamOfAndEmptyDemo
~~~

Stdout:

~~~text
Filtered: [BINH, CHI]
Single: 1
Empty: 0
Disabled: 0
Enabled: 3
~~~

**Phân tích:**

1. Stream.of ba chuỗi tạo pipeline nguồn cố định, không cần List trước.
2. filter giữ Binh, Chi vì độ dài từ 3 trở lên; map chuyển thành chữ hoa.
3. Stream.of("one") có một phần tử, nên count() là 1.
4. Stream.<String>empty() có zero elements, nên count() là 0.
5. tokens(false) trả Stream.empty(); tokens(true) trả Stream.of(...) với ba phần tử.
6. Mỗi lệnh đếm trong main được thực hiện trên **Stream mới**, không tái sử dụng một Stream đã tiêu thụ.

Điểm thiết kế quan trọng: method trả Stream rỗng khi không có dữ liệu giúp caller dùng pipeline trực tiếp mà không phải viết nhánh xử lý null.

---

## 7. Stream.builder(): nguồn phần tử được quyết định dần

Nếu các phần tử không được biết hết ngay tại một biểu thức Stream.of(...), bạn có thể dùng **Stream.builder()**.

Chữ ký tổng quát:

~~~java
public static <T> Stream.Builder<T> builder()
~~~

Builder này là một đối tượng tích lũy các phần tử kiểu T trước khi phát hành Stream.

Quy trình thường có ba bước:

1. Tạo **Stream.Builder<T>**.
2. Gọi **accept(T)** hoặc **add(T)** để thêm các phần tử theo thứ tự.
3. Gọi **build()** **một lần** để nhận Stream<T>, rồi dùng pipeline như bình thường.

Ví dụ:

~~~java
Stream.Builder<String> builder = Stream.builder();

builder.accept("Java");
builder.accept("API");

Stream<String> stream = builder.build();
~~~

Đây là đoạn minh họa. Builder có hai phần tử theo thứ tự thêm, và Stream cuối cùng có thể được filter, map hoặc collect.

### accept(T) và add(T) khác nhau thế nào?

**Stream.Builder<T>** mở rộng **Consumer<T>**, nên có:

~~~java
void accept(T t);
~~~

Ngoài ra Builder cung cấp:

~~~java
Stream.Builder<T> add(T t);
~~~

**accept(t)** thêm phần tử nhưng trả void. **add(t)** thêm phần tử rồi trả về builder, nên có thể chain:

~~~java
Stream.Builder<String> builder = Stream.builder();

builder.add("A").add("B").add("C");

Stream<String> result = builder.build();
~~~

Nếu logic dùng vòng lặp hoặc callback Consumer<T>, accept thường tự nhiên hơn. Nếu muốn một chuỗi khai báo ngắn, add có thể dễ đọc.

### Khi nào chọn builder thay vì of?

Stream.of phù hợp nhất khi đã có sẵn một số giá trị cố định:

~~~java
Stream.of("red", "green", "blue");
~~~

Builder hữu ích khi tập phần tử phụ thuộc vào nhiều điều kiện:

~~~java
Stream.Builder<String> builder = Stream.builder();

builder.accept("base");

if (includeDebug) {
    builder.accept("debug");
}

if (includeAudit) {
    builder.accept("audit");
}

Stream<String> options = builder.build();
~~~

Đây là đoạn minh họa, giả định includeDebug/includeAudit là boolean đã khai báo. Với số phần tử lớn hoặc dữ liệu thu thập qua nhiều phương thức, một Collection có thể là abstraction phù hợp hơn; builder không tự động là lựa chọn tốt nhất cho mọi việc.

## 8. Vòng đời của Stream.Builder

Builder có một ranh giới quan trọng là **build()**.

Trước build:

~~~java
Stream.Builder<String> builder = Stream.builder();
builder.accept("first");
builder.add("second");
~~~

Sau build:

~~~java
Stream<String> stream = builder.build();
~~~

Builder đã chuyển sang trạng thái **built**. Bạn không được coi nó như một container mutable có thể tiếp tục thêm giá trị hoặc xây một Stream mới từ chính builder đó.

Một lỗi thường gặp:

~~~java
builder.build();
builder.accept("late");   // Không hợp lệ theo hợp đồng Builder.
~~~

Các đoạn chỉ để minh họa. Builder sau build không phải một factory tái tạo Stream. Các lời gọi tiếp theo lên builder như accept/add/build không phải cách bắt đầu một lượt xử lý mới; implementation thông dụng báo **IllegalStateException**.

**Chú ý sự khác nhau giữa Builder và Stream:**

- **Builder** được sử dụng để lắp nguồn trước khi build.
- **Stream** được nhận từ build, dùng để thực hiện pipeline **một lần**.
- Sau khi Stream đã có terminal operation, không được dùng lại Stream đó.
- Muốn một Stream mới với cùng tập giá trị, hãy tạo **builder mới** và thêm dữ liệu lại, hoặc sử dụng một Collection có thể duyệt lại.

Không nên giữ một builder dưới dạng field dùng chung cho nhiều request rồi liên tục gọi build. Thiết kế đúng cần tạo builder riêng cho mỗi lần muốn phát sinh một Stream.

## 9. Chương trình hoàn chỉnh: builder và vòng đời

Tạo tệp **StreamBuilderDemo.java**:

~~~java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class StreamBuilderDemo {

    static Stream<String> create(boolean audit, boolean debug) {
        Stream.Builder<String> builder = Stream.builder();

        builder.accept("base");

        if (audit) {
            builder.add("audit");
        }

        if (debug) {
            builder.accept("debug");
        }

        return builder.build();
    }

    public static void main(String[] args) {
        List<String> all = create(true, true)
            .map(String::toUpperCase)
            .collect(Collectors.toList());

        List<String> minimal = create(false, false)
            .collect(Collectors.toList());

        System.out.println("All: " + all);
        System.out.println("Minimal: " + minimal);

        Stream.Builder<String> builder = Stream.builder();
        builder.add("one").add("two");

        Stream<String> stream = builder.build();
        System.out.println("Built count: " + stream.count());

        try {
            builder.accept("late");
        } catch (IllegalStateException ex) {
            System.out.println("Builder reuse: IllegalStateException");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 StreamBuilderDemo.java
java StreamBuilderDemo
~~~

Stdout trên implementation Java Stream chuẩn của JDK:

~~~text
All: [BASE, AUDIT, DEBUG]
Minimal: [base]
Built count: 2
Builder reuse: IllegalStateException
~~~

**Giải thích:**

- **create** tạo một Builder mới cho mỗi lần được gọi.
- Nếu audit và debug đều true, builder thêm base, audit, debug theo đúng thứ tự.
- Nếu cả hai false, Stream chỉ chứa base.
- **build()** phát hành Stream; count() là terminal operation tiêu thụ Stream.
- **builder.accept("late")** sau build vi phạm trạng thái builder, nên chương trình bắt IllegalStateException và in thông điệp do chúng ta định nghĩa. Không phụ thuộc vào text exception của JDK.
- Cả **create(true,true)** và **create(false,false)** cho Stream riêng, không share một builder đã build.

Đừng dùng Builder để tích lũy hàng triệu đối tượng mà không xem chi phí bộ nhớ. Stream.Builder về bản chất phải giữ các phần tử đã thêm trước khi bạn build và tiêu thụ; nó không phải cơ chế streaming I/O liên tục cho một nguồn vô hạn.

## 10. Builder và Collection: nên dùng cái nào?

Hai cách thường tạo được cùng kết quả:

**Cách A — Stream.Builder:**

~~~java
Stream.Builder<String> builder = Stream.builder();
builder.add("A").add("B");
Stream<String> result = builder.build();
~~~

**Cách B — List:**

~~~java
List<String> data = new ArrayList<>();
data.add("A");
data.add("B");
Stream<String> result = data.stream();
~~~

Đây là hai ví dụ **thay thế**, không đặt cùng tên result trong một block. Chọn theo nhu cầu:

| Nhu cầu | Builder | Collection |
| --- | --- | --- |
| Thêm từng phần tử rồi tiêu thụ đúng một pipeline | Phù hợp | Phù hợp |
| Có các nhánh if trước khi xử lý | Phù hợp | Phù hợp |
| Cần xử lý lại cùng tập dữ liệu nhiều lần | Không trực tiếp | List/Collection phù hợp hơn |
| Cần truy cập bằng index, sửa/xóa phần tử | Không cung cấp API này | List cung cấp |
| Cần lưu dữ liệu lâu dài, đi qua nhiều phương thức | Thường không thuận tiện | Collection rõ ràng hơn |
| Có sẵn 1–3 giá trị cố định | Có thể dùng nhưng dài dòng | Thường nên dùng Stream.of |
| Không có phần tử | Builder rỗng rồi build | Stream.empty đơn giản hơn |

**Builder không phải List**. Nó được thiết kế để bổ sung phần tử cho đến khi build, không cung cấp các thao tác như get(index), remove, contains hoặc iterator() của Collection.

### Không trộn nhầm quyền sở hữu

Nếu một API nhận **Stream.Builder<T>** của bên gọi rồi tự gọi build(), bên gọi không thể tiếp tục xem builder đó là đối tượng đang mở. Hãy ghi rõ ownership của builder hoặc đơn giản hơn tạo builder ngay trong method và trả về Stream kết quả.

---

## 11. Of và mảng tham chiếu: điểm dễ suy luận sai

Java có varargs overload của Stream.of. Vì thế khi đối số là **mảng**, cần nhìn chính xác kiểu generic mong muốn và loại mảng.

Với mảng tham chiếu:

~~~java
String[] words = {"A", "B"};

Stream<String> elements = Stream.of(words);
~~~

Ở đây Java có thể dùng overload varargs để tạo Stream<String> với hai phần tử **"A"**, **"B"**.

Nhưng nếu bạn muốn **một phần tử duy nhất là đối tượng mảng**, bạn phải thể hiện mục đích rõ:

~~~java
Stream<String[]> oneArray = Stream.<String[]>of(words);
~~~

Ở đây type witness **String[]** chỉ rõ T là String[], và overload một giá trị cho phép Stream chứa một mảng String[] như một phần tử.

Đối với những đoạn mã có thể gây nhầm, có thể xem trực tiếp generic type:

- **Stream<String>**: mỗi phần tử là String.
- **Stream<String[]>**: mỗi phần tử là mảng String[].

Ngoài ra:

~~~java
Stream<String> elements = Arrays.stream(words);
~~~

**Arrays.stream(String[])** là API thể hiện ý định “duyệt từng phần tử mảng” rất rõ, và có overload cho primitive arrays.

### Of với mảng primitive khác mảng tham chiếu

Với:

~~~java
int[] numbers = {1, 2, 3};
~~~

lời gọi:

~~~java
Stream<int[]> one = Stream.of(numbers);
~~~

tạo **Stream<int[]>** có một phần tử là toàn bộ mảng int[]. Primitive array **không** là một **Object[]** để varargs có thể mở rộng thành Stream<Integer>.

Muốn xử lý **từng số nguyên thủy**, dùng:

~~~java
IntStream each = Arrays.stream(numbers);
~~~

hoặc:

~~~java
IntStream each = IntStream.of(1, 2, 3);
~~~

Đây là các đoạn minh họa thay thế (không dùng cùng tên each trong một block). IntStream giúp xử lý các giá trị int trực tiếp.

**Không viết Stream<int>**, vì Java generics không chấp nhận primitive type arguments. Tùy mục đích, chọn Stream<Integer> hoặc IntStream.

## 12. Chương trình hoàn chỉnh: mảng tham chiếu, mảng primitive

Tạo tệp **StreamArraySourcesDemo.java**:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class StreamArraySourcesDemo {

    public static void main(String[] args) {
        String[] letters = {"A", "B", "C"};

        List<String> elements = Stream.of(letters)
            .collect(Collectors.toList());

        long oneArray = Stream.<String[]>of(letters).count();

        int[] numbers = {2, 4, 6};

        long primitiveArrayCount = Stream.of(numbers).count();
        int primitiveSum = Arrays.stream(numbers).sum();

        List<String> direct = Arrays.stream(letters)
            .collect(Collectors.toList());

        System.out.println("Object array elements: " + elements);
        System.out.println("Object array as one: " + oneArray);
        System.out.println("Primitive array as one: " +
            primitiveArrayCount);
        System.out.println("Primitive elements sum: " +
            primitiveSum);
        System.out.println("Arrays.stream: " + direct);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 StreamArraySourcesDemo.java
java StreamArraySourcesDemo
~~~

Stdout:

~~~text
Object array elements: [A, B, C]
Object array as one: 1
Primitive array as one: 1
Primitive elements sum: 12
Arrays.stream: [A, B, C]
~~~

**Phân tích:**

1. **Stream.of(letters)** sử dụng phần tử String trong mảng tham chiếu theo dạng varargs.
2. **Stream.<String[]>of(letters)** thể hiện rõ một phần tử kiểu String[] nên count là 1.
3. **Stream.of(numbers)** có một phần tử kiểu int[] chứ không phải ba Integer.
4. **Arrays.stream(numbers)** trả IntStream duyệt các phần tử primitive 2,4,6; sum() trả 12.
5. **Arrays.stream(letters)** trả Stream<String> cho mảng tham chiếu, dễ đọc khi muốn duyệt mảng.
6. Mỗi terminal operation được gọi trên một Stream mới.

Khi generic inference của Stream.of gặp mảng phức tạp, hãy chọn **Arrays.stream(...)** hoặc type witness rõ ràng để tránh code có ngữ nghĩa khác với ý định.

---

## 13. Null: một phần tử null không phải Stream rỗng

**Stream.empty()** có 0 phần tử. **Stream.of((String) null)** có một phần tử, và phần tử đó là null.

~~~java
long emptyCount = Stream.<String>empty().count();     // 0
long nullCount = Stream.of((String) null).count();   // 1
~~~

Điều này có thể khiến bạn bất ngờ nếu coi null là “không có dữ liệu”. Java Stream có thể chứa null; nhưng nhiều intermediate operations hoặc terminal operations sẽ không xử lý null an toàn nếu lambda của bạn giả định phần tử không null.

Ví dụ:

~~~java
Stream.of((String) null)
    .map(String::length)
    .count();
~~~

Đây là đoạn minh họa **không nên dùng làm phép kiểm tra null**. Ngoài nguy cơ NullPointerException ở phép gọi String::length nếu mapping thật sự thực thi, một số terminal operations có thể tối ưu hóa và không gọi mapper như người viết kỳ vọng. Đừng dựa vào side effect hay exception của map khi terminal operation có thể bỏ qua xử lý.

Nếu muốn loại null, hãy lọc tường minh:

~~~java
Stream.of("A", null, "B")
    .filter(java.util.Objects::nonNull)
    .forEach(System.out::println);
~~~

Đoạn minh họa trên in **A** rồi **B** trong pipeline tuần tự có encounter order. Nó loại null bằng một predicate rõ ràng.

### Null tại vị trí varargs: một lưu ý khác

Lời gọi **Stream.of(null)** có thể gây cảnh báo hoặc chọn cách diễn giải liên quan tới overload varargs khi thiếu kiểu tường minh. Không nên viết như thế nếu ý định quan trọng. Thay vào đó:

- Muốn Stream có **một phần tử null**: **Stream.of((String) null)** hoặc **Stream.<String>of((String) null)**.
- Muốn Stream **không có phần tử**: **Stream.empty()**.
- Muốn đưa mảng thành một phần tử: **Stream.<String[]>of(myArray)**.
- Muốn duyệt các phần tử của mảng: **Arrays.stream(myArray)** khi mảng tồn tại và phù hợp.

Đây là vấn đề **lựa chọn overload và kiểu generic**, không phải chỉ khác cách format code.

### Stream.ofNullable trên JDK mới

Từ **Java 9**, API **Stream.ofNullable(T)** cung cấp Stream một phần tử nếu giá trị **khác null**, hoặc Stream rỗng nếu giá trị **null**. Đây là API hiện đại vẫn được dùng, nhưng **không có trong Java 8**.

Trong chương trình phải biên dịch bằng Java 8, có thể viết factory tường minh:

~~~java
static <T> Stream<T> zeroOrOne(T value) {
    return value == null ? Stream.empty() : Stream.of(value);
}
~~~

Đây là phương thức minh họa. Cách viết này diễn đạt rõ “null nghĩa là không có phần tử”. Nó khác **Stream.of((T) null)**, vốn tạo một phần tử null.

Không khẳng định Stream.ofNullable là lỗi thời: nó là bổ sung hữu ích cho Java hiện đại; điều cần nhớ chỉ là **mốc phiên bản**.

## 14. Chương trình hoàn chỉnh: null và Stream.empty

Tạo tệp **StreamNullSemanticsDemo.java**:

~~~java
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class StreamNullSemanticsDemo {

    static <T> Stream<T> zeroOrOne(T value) {
        return value == null
            ? Stream.empty()
            : Stream.of(value);
    }

    public static void main(String[] args) {
        long empty = Stream.<String>empty().count();
        long nullElement = Stream.of((String) null).count();

        List<String> withoutNull = Stream.of(
                "Java", null, "API")
            .filter(Objects::nonNull)
            .collect(Collectors.toList());

        System.out.println("Empty count: " + empty);
        System.out.println("Null element count: " + nullElement);
        System.out.println("Filtered: " + withoutNull);
        System.out.println("Factory null: " +
            zeroOrOne((String) null).count());
        System.out.println("Factory value: " +
            zeroOrOne("ready").count());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 StreamNullSemanticsDemo.java
java StreamNullSemanticsDemo
~~~

Stdout:

~~~text
Empty count: 0
Null element count: 1
Filtered: [Java, API]
Factory null: 0
Factory value: 1
~~~

Giải thích:

- Stream.empty() không có phần tử.
- Stream.of((String) null) có một phần tử null và count là 1.
- filter(Objects::nonNull) giữ lại hai chuỗi khác null.
- zeroOrOne(null) chọn nhánh empty; zeroOrOne("ready") chọn nhánh of.
- **Không có kiểm tra null tự phát sinh trong Stream.of**. Việc xem null như “không có giá trị” phải được thể hiện tường minh bằng nhánh kiểm tra hoặc dùng ofNullable trên JDK có hỗ trợ.

## 15. Builder cũng có thể thêm null

Vì **Stream.Builder<T>.accept(T)** và **add(T)** nhận một phần tử kiểu T, builder thông thường cho phép thêm null với T là reference type. Điều này không biến builder thành một công cụ tự lọc null.

Ví dụ:

~~~java
Stream.Builder<String> builder = Stream.builder();
builder.add("A").add(null).add("B");

long count = builder.build().count(); // 3
~~~

Đây là đoạn minh họa. Kết quả count là 3 vì có ba phần tử, trong đó một phần tử null. Nếu ứng dụng không muốn null, hãy:

- Kiểm tra trước khi thêm vào builder.
- Hoặc sau khi build, dùng **filter(Objects::nonNull)** trước terminal operation.
- Hoặc chọn phương thức zeroOrOne cho các phần tử có thể vắng mặt.

Không nên đưa null vào pipeline rồi chỉ hy vọng mọi method reference đều xử lý được; ví dụ String::length không áp dụng cho null.

## 16. Stream nguồn cố định không phải Stream tái sử dụng

Xem:

~~~java
Stream<String> stream = Stream.of("A", "B");

long first = stream.count();
long second = stream.count();  // Sai.
~~~

Sau terminal operation đầu tiên, Stream đã được tiêu thụ. Trên các implementation thông dụng, lần thứ hai thường ném IllegalStateException.

Cách đúng:

~~~java
long first = Stream.of("A", "B").count();
long second = Stream.of("A", "B").count();
~~~

Ở đây mỗi dòng tạo một Stream mới.

**Lưu ý về Builder:** gọi **builder.build()** rồi thử dùng lại builder cũng không phải factory tạo Stream mới. Nếu cần nhiều Stream có cùng các giá trị:

~~~java
Supplier<Stream<String>> factory =
    () -> Stream.of("A", "B");
~~~

Đây là đoạn minh họa cần import java.util.function.Supplier. Mỗi lần **factory.get()** tạo Stream mới vì **Stream.of(...) nằm trong thân lambda**.

Không nên:

~~~java
Stream<String> old = Stream.of("A", "B");

Supplier<Stream<String>> broken = () -> old;
~~~

broken.get() luôn trả cùng đối tượng Stream cũ. Bọc một Stream trong Supplier không làm nó reusable.

## 17. Chương trình hoàn chỉnh: tạo Stream mới cho mỗi lần dùng

Tạo tệp **StreamSourceFactoryDemo.java**:

~~~java
import java.util.List;
import java.util.function.Supplier;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class StreamSourceFactoryDemo {

    static Stream<String> buildFresh() {
        Stream.Builder<String> builder = Stream.builder();
        builder.add("one").add("two");
        return builder.build();
    }

    public static void main(String[] args) {
        Supplier<Stream<String>> fixed =
            () -> Stream.of("A", "B", "C");

        long first = fixed.get().count();
        long second = fixed.get().count();

        List<String> names = buildFresh()
            .map(String::toUpperCase)
            .collect(Collectors.toList());

        long again = buildFresh().count();

        System.out.println("First: " + first);
        System.out.println("Second: " + second);
        System.out.println("Built names: " + names);
        System.out.println("Fresh builder count: " + again);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 StreamSourceFactoryDemo.java
java StreamSourceFactoryDemo
~~~

Stdout:

~~~text
First: 3
Second: 3
Built names: [ONE, TWO]
Fresh builder count: 2
~~~

**Phân tích:**

1. fixed.get() gọi lại **Stream.of(...)** và tạo một Stream mới ở mỗi lần.
2. buildFresh() tạo một **Builder mới**, thêm dữ liệu, gọi build và trả một Stream mới.
3. Việc main gọi buildFresh() hai lần hợp lệ vì mỗi lần có một Builder và Stream riêng.
4. Nếu buildFresh() giữ builder trong một biến static rồi gọi build nhiều lần, thiết kế sẽ sai.
5. Đây là cách đơn giản để xây API cần tạo Stream theo một quy trình cố định nhiều lần mà không tái sử dụng nguồn Stream đã tiêu thụ.

---

## 18. Khi nào nên dùng IntStream, LongStream và DoubleStream?

**Stream.of(...)** tạo **Stream<T>** với các wrapper reference types khi truyền primitive values như int, long, double.

Nếu làm các phép toán số, Java có primitive stream:

~~~java
IntStream.of(1, 2, 3).sum();

LongStream.of(10L, 20L).sum();

DoubleStream.of(1.5, 2.5).average();
~~~

Các đoạn này là minh họa cần import những primitive stream tương ứng.

| Nhu cầu | Lựa chọn |
| --- | --- |
| Một vài String/object | Stream.of(...) |
| Không có object elements | Stream.empty() |
| Thêm Object phần tử dần rồi build | Stream.builder() |
| Giá trị int, tính sum/min/max | IntStream.of(...) |
| Giá trị long | LongStream.of(...) |
| Giá trị double | DoubleStream.of(...) |
| Duyệt primitive array | Arrays.stream(int[]/long[]/double[]) |
| Duyệt object array | Arrays.stream(T[]) hoặc Stream.of(T[] varargs) |

**Primitive streams cũng single-use.** Chúng không tự tái sử dụng được sau terminal operation.

Không có **Stream<int>** hợp lệ vì Java generics không nhận primitive type arguments. Tránh chuyển các primitive sang Integer rồi lại unbox không cần thiết nếu bài toán chỉ cần xử lý số nguyên thủy.

## 19. So sánh three factories theo trường hợp sử dụng

| Tiêu chí | Stream.of(...) | Stream.empty() | Stream.builder() |
| --- | --- | --- | --- |
| Số phần tử | 1, nhiều, hoặc 0 qua varargs | Luôn 0 | Tùy số lần accept/add |
| Nguồn đầu vào | Giá trị truyền ngay tại lời gọi | Không có giá trị | Các giá trị tích lũy trước build |
| Kiểu kết quả | Stream<T> | Stream<T> | Stream<T> sau build |
| Dùng cho điều kiện if | Có thể nhưng dễ dài | Tốt cho nhánh không dữ liệu | Tốt khi quyết định nhiều phần tử |
| Có thể dùng lại Stream đã tiêu thụ? | Không | Không | Không |
| Có thể dùng lại Builder sau build? | Không có Builder | Không có Builder | Không |
| Null được xem là 0 phần tử? | Không; typed null có thể là 1 phần tử | Luôn 0 | Không tự loại null |
| Dễ đọc nhất khi | Các giá trị có sẵn | Không có phần tử | Thêm phần tử theo từng điều kiện |

### Cách chọn nhanh

- Đã biết các phần tử: **Stream.of("A","B")**.
- Không có phần tử: **Stream.empty()**.
- Điều kiện quyết định thêm nhiều giá trị: **Stream.builder()**, tạo builder riêng.
- Đã có List/Set: thường **collection.stream()** tự nhiên hơn.
- Đã có mảng: **Arrays.stream(array)** rất rõ ý định duyệt từng phần tử.
- Có số nguyên thủy: cân nhắc **IntStream.of(...)** và primitive stream khác.
- Muốn xử lý cùng dữ liệu nhiều lượt: **tạo Stream mới** mỗi lần, không giữ một Stream cũ.

---

## 20. Những lỗi phổ biến

| Lỗi | Tại sao sai | Cách sửa |
| --- | --- | --- |
| Nghĩ Stream.of(list) duyệt từng phần tử List | Nó có thể tạo Stream<List<T>> một phần tử | Dùng list.stream() |
| Nghĩ Stream.of(int[]) cho nhiều Integer | int[] là một đối tượng mảng | Dùng Arrays.stream(int[]) |
| Nghĩ Stream.of((String)null) là rỗng | Đây là Stream chứa một null | Dùng Stream.empty() hoặc zeroOrOne |
| Dùng Stream.of(null) không làm rõ overload | Có thể gặp cảnh báo/nhầm varargs | Ép kiểu typed null hoặc dùng empty |
| Gọi terminal operation hai lần | Stream single-use | Tạo Stream mới |
| Tạo hai nhánh từ cùng Stream base | Không được fork một Stream tùy tiện | Gọi nguồn factory hai lần |
| Gọi builder.accept sau build | Builder không tiếp tục nhận phần tử sau build | Tạo builder mới |
| Gọi builder.build hai lần | Builder không phải Stream factory | Tạo Builder mới cho mỗi Stream |
| Giữ builder dùng chung giữa nhiều request | Trạng thái builder không có hợp đồng reusable | Builder riêng, scoped cục bộ |
| Dùng builder để giữ kho dữ liệu lâu dài | Builder không hỗ trợ Collection operations | Dùng Collection |
| Dùng Stream.empty() rồi mong có dữ liệu về sau | Stream đã tạo với 0 phần tử | Tạo Stream mới khi dữ liệu có |
| Quên type parameter cần thiết | Suy luận generic có thể không đúng ý | Khai báo Stream<T> hoặc type witness |
| Dùng raw Stream để tránh lỗi generic | Mất type safety, cảnh báo unchecked | Dùng generic T cụ thể |
| Dùng String::length trên phần tử null | Có thể NPE khi mapping thực thi | Lọc null hoặc thiết kế null policy |
| Lạm dụng builder cho một literal | Dài dòng, khó đọc | Stream.of(literal) |
| Nghĩ Stream.ofNullable có trong Java 8 | API xuất hiện từ Java 9 | Dùng nhánh empty/of khi JDK 8 |
| Nghĩ Stream.toList() có trong Java 8 | API xuất hiện từ Java 16 | Dùng collect(Collectors.toList()) |
| Dùng peek side effect để kiểm chứng số phần tử | Optimization có thể bỏ qua xử lý | Dùng terminal operation có hợp đồng |
| Giả định mọi Stream đều chạy parallel | Các factories này tạo sequential streams | Chỉ chuyển parallel khi thật sự cần và đo đạc |

## 21. Type erasure, nullability và an toàn kiểu

Một Stream generic kiểm tra kiểu ở compile time nhưng Java generics vẫn chịu **type erasure** trong runtime. Viết **Stream<String>** không có nghĩa JVM tự cấm null hay sinh một runtime class đặc biệt cho mỗi type argument.

Ví dụ:

~~~java
Stream<String> names = Stream.of("A", "B");
~~~

trình biên dịch kiểm tra phần tử phù hợp String. Nếu code sử dụng raw types/unchecked casts, có thể phá vỡ tính an toàn kiểu và gặp ClassCastException trong đường thực thi về sau.

**Null policy là một quyết định khác với generic type.** Một Stream<String> có thể chứa null. Nếu hợp đồng dữ liệu không cho phép null, hãy xử lý ở nguồn, filter hoặc validation; không suy luận rằng chữ String trong Stream<String> tự chặn null.

**Stream.empty() vẫn là Stream<T>.** Nó không tương đương một biến null và có thể được truyền cho API nhận Stream<T> mà không cần nhánh null.

## 22. Tính lazy và những kỳ vọng sai về side effect

Các factories **of**, **empty**, **builder.build()** tạo nguồn Stream. Phần lớn intermediate operations không thực thi toàn bộ việc xử lý ngay tại lúc xây pipeline.

~~~java
Stream<String> pipeline = Stream.of("A", "B", "C")
    .filter(s -> {
        System.out.println("Filtering: " + s);
        return true;
    });
~~~

Đây là đoạn minh họa có side effect. Khi mới xây pipeline, phần filter chưa nhất thiết chạy. Khi gọi terminal operation, pipeline có thể được đánh giá; nhưng không nên dựa vào số lần side-effect chạy nếu Stream implementation có thể tối ưu dựa trên thông tin kích thước nguồn hoặc short-circuit.

Ví dụ những lời gọi **count()** trên một số pipeline đã biết số lượng phần tử có thể được tối ưu mà không cần chạy tất cả intermediate operations, tùy đặc tính Stream và phiên bản JDK.

**Nguyên tắc:** ưu tiên lambdas không có side effect trong filter/map; nếu cần đếm thì dùng count(), nếu cần thu kết quả thì dùng collect, nếu cần xử lý từng phần tử thì dùng forEach/forEachOrdered theo hợp đồng thứ tự.

Việc pipeline lazy không thay đổi quy tắc **Stream chỉ được vận hành một lần**. Ngay cả khi một terminal operation chỉ xem phần đầu dữ liệu, Stream vẫn đã được tiêu thụ.

## 23. Bài tập thực hành có đáp án

### Bài 1 — Một giá trị hay Collection bên trong Stream?

~~~java
List<String> xs = Arrays.asList("X", "Y");
long count = Stream.of(xs).count();
~~~

**Đáp án:** count = **1** vì Stream có một phần tử là List<String>. Nếu muốn hai String, dùng xs.stream().

### Bài 2 — Stream.empty hay Stream.of(null)?

~~~java
long a = Stream.<String>empty().count();
long b = Stream.of((String) null).count();
~~~

**Đáp án:** a = **0**, b = **1**. Null là giá trị phần tử chứ không tự biến thành Stream rỗng.

### Bài 3 — Builder với hai điều kiện

Bạn muốn luôn thêm "base", thêm "audit" nếu bật audit, và "debug" nếu bật debug. Hãy dùng builder.

**Đáp án:**

~~~java
Stream.Builder<String> builder = Stream.builder();
builder.add("base");

if (audit) {
    builder.add("audit");
}
if (debug) {
    builder.add("debug");
}

Stream<String> result = builder.build();
~~~

Đây là đoạn minh họa, cần khai báo audit/debug. Builder được build một lần.

### Bài 4 — Vì sao sau build không add tiếp?

**Đáp án:** Builder chuyển sang trạng thái built. Nó không phải Collection để thêm phần tử mãi mãi. Muốn có pipeline mới, tạo builder mới hoặc dùng Collection làm nguồn có thể duyệt lại.

### Bài 5 — Array varargs

Cho **String[] words = {"A","B"}**. Hai lời gọi **Stream.of(words)** và **Stream.<String[]>of(words)** khác nhau thế nào?

**Đáp án:** trong ngữ cảnh tương ứng, lời gọi thứ nhất có thể cung cấp Stream<String> gồm A và B; lời gọi có type witness String[] thể hiện Stream<String[]> chứa một mảng. Dùng Arrays.stream(words) nếu ý định là các String.

### Bài 6 — Mảng int

Cho **int[] data = {1,2,3}**. **Stream.of(data).count()** trả bao nhiêu?

**Đáp án:** **1**; Stream chứa một int[]. Muốn sum các phần tử, dùng Arrays.stream(data).sum(), kết quả **6**.

### Bài 7 — Tạo Stream mới hai lần

~~~java
Stream<String> s = Stream.of("A","B");
long first = s.count();
long second = s.count();
~~~

**Đáp án:** không hợp lệ về cách sử dụng Stream. Tạo Stream.of(...) riêng cho mỗi lượt; không gọi lại s.

### Bài 8 — Supplier có tự tái tạo Stream không?

~~~java
Stream<String> old = Stream.of("A");
Supplier<Stream<String>> supplier = () -> old;
~~~

**Đáp án:** không. Mỗi get() trả cùng Stream cũ. Viết **() -> Stream.of("A")** mới thật sự tạo Stream mới.

### Bài 9 — Chọn primitive stream

Bạn muốn tổng các giá trị int 1,2,3 mà không tạo Stream<Integer>. Dùng gì?

**Đáp án:** **IntStream.of(1,2,3).sum()**, kết quả 6.

### Bài 10 — Dự án vẫn dùng JDK 8

Bạn có thể dùng Stream.ofNullable(value) và Stream.toList() trong code target JDK 8 không?

**Đáp án:** không. Stream.ofNullable có từ Java 9; Stream.toList từ Java 16. Với JDK 8, dùng nhánh **value == null ? Stream.empty() : Stream.of(value)** và **collect(Collectors.toList())** nếu cần List.

### Bài 11 — Empty branch

Một method trả Stream<String>. Khi không có dữ liệu, nên trả null hay Stream.empty()?

**Đáp án:** Stream.empty() thường tốt hơn nếu hợp đồng là trả một pipeline hợp lệ. Caller không cần kiểm tra null trước khi filter, map hay count.

### Bài 12 — Khi nào nên tạo Collection?

Dữ liệu được thêm dần và bạn muốn xử lý ba lần, đồng thời truy cập phần tử theo index. Dùng Stream.builder() hay List?

**Đáp án:** **List** phù hợp hơn. Sau khi xây xong, gọi list.stream() mới cho mỗi lượt.

## 24. Checklist áp dụng trong dự án

**Trước khi chọn factory:**

- Các giá trị đã biết ngay chưa?
- Trường hợp không dữ liệu có nên biểu diễn bằng Stream.empty()?
- Có nhiều điều kiện quyết định phần tử nên dùng Stream.builder()?
- Nguồn là một List hoặc mảng đã tồn tại, có nên stream() hay Arrays.stream() trực tiếp?
- Phần tử là primitive hay reference type?
- Null được phép xuất hiện trong Stream hay phải bị loại?

**Khi xử lý generic và mảng:**

- Stream<T> có T là phần tử thật hay T là một mảng/Collection?
- Có cần type witness để tránh hiểu nhầm overload varargs?
- Với mảng primitive, đã chọn Arrays.stream hoặc primitive stream chưa?
- Có dùng raw type hoặc unchecked cast không cần thiết không?

**Khi dùng builder:**

- Builder có được tạo mới cho mỗi lượt không?
- Mọi lời gọi add/accept đã hoàn tất trước build chưa?
- build() chỉ được gọi một lần trên builder?
- Không có đoạn code cố sử dụng lại builder sau build?

**Khi chạy pipeline:**

- Mỗi Stream có một terminal operation phù hợp?
- Có vô tình dùng lại một Stream sau count/collect/findFirst/close không?
- Có side effect ở filter/map gây phụ thuộc vào optimizer?
- Nếu cần nhiều lượt, có factory tạo Stream mới hoặc Collection nguồn không?

**Khi bảo trì phiên bản Java:**

- API được dùng có tồn tại ở phiên bản JDK tối thiểu của dự án?
- Stream.ofNullable và Stream.toList được phân biệt rõ với các API Java 8?
- Test có kiểm tra số phần tử, kiểu phần tử và null policy?

## Tổng kết

**Stream.of(...)** tạo Stream từ các giá trị cụ thể; **Stream.empty()** tạo Stream không có phần tử; **Stream.builder()** thu thập giá trị theo từng bước trước khi trả Stream bằng **build()**. Cả ba là các nguồn Stream hợp lệ từ Java 8 và vẫn phù hợp trong Java hiện đại.

Hãy nhớ ba điểm dễ nhầm nhất: **Stream.of(collection)** thường chứa **một Collection** chứ không duyệt các phần tử bên trong; **Stream.of((String)null)** chứa **một null**, còn **Stream.empty()** chứa không phần tử; và **Stream.Builder** không phải đối tượng tái sử dụng sau build.

Với mảng, kiểm tra kỹ loại mảng và overload varargs; ưu tiên **Arrays.stream(...)** khi muốn duyệt từng phần tử. Với số nguyên thủy, chọn **IntStream/LongStream/DoubleStream** khi phù hợp. Với nhiều lượt xử lý, **tạo Stream mới** mỗi lần hoặc giữ Collection làm nguồn thay vì cố dùng lại Stream hoặc builder cũ.

Cuối cùng, các factories này **không tự thực thi validation**, không đảm bảo null-free và không thay đổi quy tắc pipeline lazy/single-use. Hiểu rõ kiểu phần tử, số phần tử, vòng đời builder và cách tạo nguồn mới sẽ giúp viết Java Stream chính xác, dễ đọc và bền vững.