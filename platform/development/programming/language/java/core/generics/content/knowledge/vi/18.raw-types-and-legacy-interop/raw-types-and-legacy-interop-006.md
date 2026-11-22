# Nguy cơ trộn dữ liệu sai kiểu và lỗi xuất hiện muộn khi dùng kiểu thô trong Java Generics

## Mục tiêu học tập

Kiểu thô (*raw type*) là tên của một kiểu generic được dùng **mà không cung cấp đối số kiểu**: viết `List` thay cho `List<String>`, `Map` thay cho `Map<String, Integer>`. Java vẫn hỗ trợ cú pháp này chủ yếu để tương thích với thư viện, mã nguồn cũ trước generics. Nhưng khi dùng kiểu thô để ghi dữ liệu, những bảo đảm về kiểu phần tử có thể bị phá vỡ mà chương trình vẫn biên dịch và tiếp tục chạy.

Sau bài này, bạn có thể:

- Phân biệt `List<String>`, raw `List`, `List<?>` và `List<Object>`.
- Giải thích cơ chế **heap pollution**: đối tượng thực tế chứa phần tử không đúng với kiểu generic mà một tham chiếu khác đang tin tưởng.
- Mô tả vì sao một lời gọi `add` có thể thành công nhưng `ClassCastException` chỉ nổ ở thao tác `get`, vòng lặp hoặc tầng nghiệp vụ chạy sau đó.
- Đọc đúng các cảnh báo `rawtypes`, `unchecked` và bytecode `checkcast`.
- Sửa ranh giới API bằng kiểu tham số hóa, wildcard đúng mục đích, xác thực phần tử và các collection được kiểm tra kiểu lúc chạy khi thật sự cần.

## 1. Vì sao raw alias có thể khiến lỗi lộ rất muộn?

Một `List<String>` có contract phần tử `String` ở compile time. Nếu một tham chiếu khác nhìn **chính object ấy** dưới dạng raw `List`, Java cho phép gọi `add` theo erasure của method `List.add(E)` và thường chỉ báo unchecked warning:

```java
List<String> cities = new ArrayList<>();
cities.add("Ha Noi");
List rawAlias = cities; // Không tạo bản sao
rawAlias.add(42);       // Lời gọi unchecked
```

Đây là snippet trong method với imports `java.util.List` và `java.util.ArrayList`. Mặc dù hiện tại `cities` được khai báo typed, `rawAlias` đã đưa một phần tử `Integer` vào object đang dùng chung. **Không có phép kiểm tra `String.class` tự động ở raw `ArrayList.add`**. Hành vi sai chỉ bị lộ khi một downstream operation đòi hỏi `String` cụ thể.

So sánh nhanh: `List<?>` giữ quyền đọc dưới `Object` nhưng không cho thêm non-null tùy ý; `List<Object>` được tham số hóa `Object` thực sự và không nhận trực tiếp `List<String>` vì invariance. Điểm trung tâm của bài này là **truy vết từ điểm ghi sai đến vị trí cast thất bại**, thay vì chỉ ghi nhớ định nghĩa raw type.

## 2. Tình huống cốt lõi: chèn sai kiểu bây giờ, lỗi xảy ra sau

Ví dụ minh họa nằm **bên trong một phương thức**, với các import thích hợp:

```java
List<String> cities = new ArrayList<>();
cities.add("Ha Noi");

List raw = cities;
raw.add(42);             // Lời gọi unchecked; có thể chạy thành công.

String first = cities.get(0);  // "Ha Noi", vẫn hợp lệ.
String second = cities.get(1); // ClassCastException lúc đọc Integer thành String.
```

Điểm bất thường: tại dòng `raw.add(42)`, Java không tự động ném `ClassCastException` chỉ vì có một tham chiếu `List<String>` tới cùng đối tượng. Raw `List` có phương thức `add(Object)` sau erasure; `Integer.valueOf(42)` cũng là `Object` nên có thể được lưu trong một `ArrayList` thông thường.

Khi tới dòng `String second = cities.get(1)`, chương trình cần tin rằng phần tử là `String`. Trình biên dịch chèn phép cast từ giá trị trả về `Object` của `List.get(int)` sang `String`. Vì phần tử thật là `Integer`, cast thất bại **tại điểm đọc**, có thể nằm rất xa nơi ghi sai dữ liệu.

Đó là nguồn gốc của lỗi **xuất hiện muộn** (*delayed failure*): thao tác làm hỏng bất biến xảy ra ở một thời điểm, còn ngoại lệ được kích hoạt ở lần dùng tiếp theo đòi hỏi một kiểu cụ thể.

Lời gọi không an toàn được cảnh báo khi biên dịch, nhưng **cảnh báo không phải ngoại lệ runtime**. Compiler vẫn tạo class file và JVM chạy tiếp trừ khi bạn cấu hình quy trình build từ chối cảnh báo.

## 3. Heap pollution: vì sao dữ liệu và kiểu tham chiếu có thể mâu thuẫn?

*Heap pollution* trong ngữ cảnh Java generics là tình huống một biến thuộc kiểu được tham số hóa lại tham chiếu đến đối tượng không phù hợp với kiểu tham số hóa đó. Trong ví dụ trên:

```text
Danh sách ArrayList thực tế:
index 0 -> String("Ha Noi")
index 1 -> Integer(42)

Một tham chiếu đang tin:
List<String> cities
  └── mọi phần tử được lấy để dùng như String

Một tham chiếu raw cùng trỏ vào đối tượng:
List raw
  └── add(Object) đã chèn Integer

Đọc từ cities:
get(1) trả về Object(Integer)
    ↓
compiler chèn checkcast String
    ↓
ClassCastException
```

Vì hai tham chiếu giữ **cùng một đối tượng**, không thể sửa lỗi chỉ bằng cách đổi tên biến hoặc ép kiểu tham chiếu:

```java
// Không phải biện pháp sửa lỗi:
List<String> anotherView = cities;
```

`anotherView` chỉ là một alias khác, cũng nhìn danh sách bị ô nhiễm. Việc cast một collection sang `List<String>` thông qua unchecked cast cũng **không** quét và xác minh tất cả phần tử bên trong.

Một số đặc điểm đáng nhớ:

1. Lỗi có thể ẩn rất lâu nếu ứng dụng mới đọc những phần tử hợp lệ trước tiên.
2. Nếu code chỉ in `list.size()` hoặc truyền danh sách qua các tầng mà chưa đòi hỏi `String`, chưa chắc sẽ có ngoại lệ.
3. Lỗi có thể xuất hiện tại một service, formatter, mapper, consumer hoặc vòng lặp khác, khiến người debug nghi ngờ nhầm tầng đó.
4. Vị trí phát hiện sai kiểu thường là lệnh cast do compiler chèn ở **nơi đọc**, không phải câu lệnh raw `add` đã làm hỏng dữ liệu.
5. Heap pollution không chỉ đến từ raw collection: unchecked cast, varargs generic không an toàn và những ranh giới dùng reflection/API legacy cũng có thể tạo điều kiện tương tự.

## 4. Ví dụ Java 17 hoàn chỉnh: phát hiện muộn và phòng vệ sớm

Chương trình sau cố ý tạo dữ liệu sai kiểu qua raw `List` để chứng minh lỗi trì hoãn, sau đó minh họa hai cách bảo vệ: **kiểm tra dữ liệu khi nhận từ nguồn chưa rõ kiểu** và **runtime checked collection**.

**Tệp `RawTypeRiskDemo.java`:**

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;

public class RawTypeRiskDemo {
    static List<String> validatedCopy(List<?> input) {
        List<String> result = new ArrayList<>();
        for (Object element : input) {
            if (!(element instanceof String text)) {
                String found = element == null
                        ? "null" : element.getClass().getSimpleName();
                throw new IllegalArgumentException(
                        "Expected String, found " + found);
            }
            result.add(text);
        }
        return List.copyOf(result);
    }

    public static void main(String[] args) {
        List<String> cities = new ArrayList<>(List.of("Ha Noi", "Hue"));
        List raw = cities;
        raw.add(42);
        System.out.println("size=" + cities.size());
        System.out.println("first=" + cities.get(0));

        try {
            for (String city : cities) {
                System.out.println("upper=" + city.toUpperCase(Locale.ROOT));
            }
        } catch (ClassCastException exception) {
            System.out.println("late error="
                    + exception.getClass().getSimpleName());
            System.out.println("late frame="
                    + exception.getStackTrace()[0].getMethodName());
        }

        List<?> observed = cities;
        System.out.println("third type="
                + observed.get(2).getClass().getSimpleName());

        try {
            validatedCopy(observed);
        } catch (IllegalArgumentException exception) {
            System.out.println("validation=" + exception.getMessage());
        }
        System.out.println("clean=" + validatedCopy(List.of("Da Nang", "Hue")));

        List<String> guarded = Collections.checkedList(
                new ArrayList<>(), String.class);
        List rawGuarded = guarded;
        rawGuarded.add("Safe");
        try {
            rawGuarded.add(42);
        } catch (ClassCastException exception) {
            System.out.println("guarded error="
                    + exception.getClass().getSimpleName());
        }
        System.out.println("guarded=" + guarded);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 RawTypeRiskDemo.java
java RawTypeRiskDemo
```

`javac` có thể in ghi chú về unchecked/unsafe operations khi biên dịch; đây là hệ quả cố ý của raw type. **Stdout của lệnh `java`** đã được kiểm chứng:

```text
size=3
first=Ha Noi
upper=HA NOI
upper=HUE
late error=ClassCastException
late frame=main
third type=Integer
validation=Expected String, found Integer
clean=[Da Nang, Hue]
guarded error=ClassCastException
guarded=[Safe]
```

Tại sao đầu ra đúng như vậy?

- `raw.add(42)` tăng kích thước danh sách lên ba phần tử mà chưa ném exception.
- `cities.get(0)` trả về phần tử chuỗi ở đầu, nên vẫn in `Ha Noi`.
- Vòng lặp `for (String city : cities)` xử lý hai chuỗi đầu tiên. Đến phần tử `Integer` thứ ba, cast sang `String` thất bại. Ngoại lệ được bắt và in `late error=ClassCastException`; phương thức chứa lệnh cast là `main`.
- `List<?> observed` chỉ đọc phần tử dưới dạng `Object`, vì thế `observed.get(2).getClass()` nhìn được lớp runtime `Integer` mà không yêu cầu cast sang `String`.
- `validatedCopy` duyệt tất cả phần tử, kiểm tra từng phần tử bằng `instanceof String` và dừng với thông báo có ý nghĩa ngay tại ranh giới xác thực.
- `Collections.checkedList(..., String.class)` tạo một **wrapper kiểm tra kiểu lúc cập nhật qua wrapper**. `rawGuarded.add(42)` bị ném CCE ngay lúc ghi, khiến danh sách `guarded` chỉ còn phần tử hợp lệ `Safe`.

Ví dụ `validatedCopy` dùng *pattern matching for instanceof*, tính năng chính thức trên Java 17. `List.copyOf` trả về danh sách không sửa được và từ chối giá trị `null`; trong hàm này, `null` đã bị chặn ở bước `instanceof` nên hợp đồng đầu ra là danh sách chỉ gồm String không null.

**Không bỏ các lệnh raw khỏi chương trình nếu muốn tái tạo lỗi**: mục đích của ví dụ là chứng minh nguy cơ. Khi áp dụng trong ứng dụng thật, thay chúng bằng các API có generic chính xác.

## 5. Vì sao lỗi không nổ ngay ở `add`?

Có ba cấp độ khác nhau:

### 5.1. Hợp đồng ở mã nguồn

Với:

```java
List<String> names = new ArrayList<>();
// names.add(42); // Compile error.
```

compiler hiểu `names.add(...)` cần đối số `String`. Một literal số nguyên 42 được boxing thành `Integer`, không phù hợp `String`, nên chương trình bị từ chối từ compile time.

### 5.2. Lời gọi trên raw type

Với:

```java
List raw = names;
raw.add(42); // Unchecked warning.
```

thao tác trên raw `List` không còn ràng buộc đầu vào theo `String`. `ArrayList` mặc định lưu tham chiếu đối tượng, không tự mang cơ chế kiểm tra `String.class` trên từng lần thêm. Vì vậy thêm `Integer` có thể thành công và làm ô nhiễm danh sách.

### 5.3. Cast được compiler chèn khi đọc

Lúc đọc:

```java
String result = names.get(0);
```

ở góc nhìn bytecode, phương thức `List.get(int)` có descriptor trả về `Object`. Compiler chèn `checkcast String` trước khi gán vào `result`. Nếu phần tử thực không là `String`, JVM ném `ClassCastException` tại đây.

**Khác biệt cốt lõi:** erasure không có nghĩa là JVM hoàn toàn không kiểm tra kiểu. JVM vẫn kiểm tra các phép cast tham chiếu **cụ thể**; điều bị mất là khả năng đảm bảo tự động rằng một collection generic bị dùng bằng raw type sẽ giữ đúng tham số kiểu của các tham chiếu khác.

## 6. Quan sát bằng cảnh báo trình biên dịch và bytecode

### 6.1. Bật các cảnh báo có liên quan

Chạy:

```bash
javac --release 17 -Xlint:rawtypes,unchecked RawTypeRiskDemo.java
```

Các cảnh báo quan trọng của chương trình:

| Vị trí | Loại cảnh báo | Ý nghĩa |
| --- | --- | --- |
| `List raw = cities;` | `[rawtypes]` | Tên kiểu generic được dùng mà không ghi đối số kiểu. |
| `raw.add(42);` | `[unchecked]` | Lời gọi `add(E)` trên raw `List`; compiler không chứng minh được dữ liệu phù hợp. |
| `List rawGuarded = guarded;` | `[rawtypes]` | Vẫn là khai báo raw, dù đối tượng thật là checked wrapper. |
| `rawGuarded.add(...)` | `[unchecked]` | Compiler không thể xác nhận lời gọi raw là an toàn; checked wrapper kiểm tra ở runtime. |

Trong bản chạy đã kiểm chứng, lệnh lint trên báo năm cảnh báo: hai cảnh báo rawtypes và ba cảnh báo unchecked cho các lời gọi `add` thông qua biến raw. Số cảnh báo hoặc cách diễn đạt có thể khác khi thay đổi chương trình hoặc phiên bản trình biên dịch.

Sự khác nhau giữa hai cờ:

- `rawtypes` giúp tìm những chỗ **bỏ tham số generic**.
- `unchecked` giúp tìm những thao tác mà compiler **không kiểm tra được hoàn toàn**, đặc biệt lời gọi qua raw type và phép chuyển đổi generic không an toàn.

Một cảnh báo unchecked **không khẳng định lệnh sẽ luôn ném ngoại lệ**. Nó chỉ nói compiler không thể bảo đảm điều đó là an toàn. `rawGuarded.add("Safe")` vẫn thành công; `rawGuarded.add(42)` ném CCE do checked wrapper.

### 6.2. Xem vị trí cast thực tế

Biên dịch chương trình phần 4 rồi chạy:

```bash
javap -c -p RawTypeRiskDemo
```

Trong bytecode của `main`, hãy tìm `invokeinterface java/util/List.get` hoặc `java/util/Iterator.next` và `checkcast java/lang/String` ngay sau kết quả lấy từ danh sách.

Một đoạn logic tương đương:

```text
invokeinterface java/util/Iterator.next:()Ljava/lang/Object;
checkcast java/lang/String
astore ...
```

Đây là **trích yếu minh họa**; các chỉ số local variable và constant pool tùy bản biên dịch. Với chương trình đã kiểm chứng, `javap` thực sự cho thấy `checkcast java/lang/String` ở vị trí đọc kết quả `List.get` và trong vòng lặp sau `Iterator.next`.

Nhờ đó, bạn có thể tách biệt:

- **Lỗi được gây ra ở đâu?** Raw `add` đưa `Integer` vào cấu trúc có hợp đồng `List<String>`.
- **Lỗi bị phát hiện ở đâu?** Lệnh `checkcast` sau khi đọc qua tham chiếu có kiểu `List<String>`.
- **Lỗi hiện trong stack trace ở đâu?** Thường ở phương thức chứa thao tác đọc/cast, như `RawTypeRiskDemo.main` trong chương trình này.

Khi stack trace báo lỗi ở service đọc dữ liệu, đừng vội sửa dòng `get` bằng cast khác. Hãy truy ngược những nơi đã thêm phần tử hoặc nhận dữ liệu không được xác thực.

## 7. Lỗi xuất hiện muộn qua nhiều tầng ứng dụng

Trong dự án thực tế, thao tác gây heap pollution và thao tác phát hiện có thể thuộc các tầng khác nhau.

Sơ đồ:

```text
Adapter legacy / API chưa tham số hóa
  |
  | ghi Integer vào collection tưởng là List<String>
  v
Cache / state / DTO nội bộ
  |
  | truyền qua nhiều phương thức, chưa đọc phần tử
  v
Service nghiệp vụ
  |
  | đọc String, áp dụng String::trim / toUpperCase
  v
checkcast String thất bại
  |
  v
ClassCastException trong Service
```

Ví dụ với một `Map`:

```java
// Đoạn minh họa bên trong một phương thức:
Map<String, Integer> ages = new HashMap<>();
Map rawAges = ages;
rawAges.put("Mai", "unknown"); // unchecked: giá trị String thay vì Integer

Integer age = ages.get("Mai"); // CCE khi kết quả Object bị cast Integer
```

Cần import `java.util.Map` và `java.util.HashMap` nếu tách thành chương trình riêng. `HashMap` thông thường không kiểm tra cặp generic `String, Integer` ở runtime. Giá trị sai được ghi, đến lúc caller kỳ vọng `Integer` thì cast thất bại.

Nếu một component khác chỉ gọi `ages.containsKey("Mai")`, có thể chưa gặp vấn đề dù dữ liệu đã sai. Điều này lý giải vì sao stack trace ở component đọc không nhất thiết trỏ đến nguồn gây lỗi.

Một trường hợp khác là ranh giới API legacy:

```java
// API cũ, minh họa:
static List fetchLegacyRows() {
    return new ArrayList();
}

// Caller:
// List<String> rows = fetchLegacyRows(); // unchecked conversion
```

Ngay tại câu lệnh gán, Java không duyệt từng phần tử để xác thực chúng đều là `String`. Nếu trong danh sách có một phần tử khác kiểu, lỗi sẽ phát sinh khi chương trình sử dụng phần tử ở vai trò `String`.

Trong các hệ thống dùng cache, hàng đợi, callback hoặc chạy song song, khoảng cách thời gian có thể lớn hơn nữa. Raw type **không đồng nghĩa với lỗi đồng thời**; ở đây vấn đề chính vẫn là mất ràng buộc kiểu, không phụ thuộc có nhiều luồng hay không.

## 8. Wildcard giúp chặn lần ghi sai mới, không làm sạch heap pollution cũ

Nếu một thành phần chỉ quan sát danh sách chưa biết element type, nhận `List<?>` thay vì raw `List`:

```java
static void reportValues(List<?> source) {
    for (Object value : source) {
        System.out.println(value);
    }
}
```

Method cần import `java.util.List` và đặt trong class. Wildcard ngăn caller của method này thêm một `String` hoặc `Integer` tùy ý **thông qua tham chiếu `List<?>`**. Nó không có nghĩa `source` immutable: việc `clear()` hoặc `remove(index)` vẫn được compiler cho phép theo contract của `List`, tùy runtime mutability.

Đặc biệt, nếu một raw alias **đã** làm ô nhiễm `List<String>`, chuyển góc nhìn sang `List<?>` sẽ không xóa phần tử `Integer` đang có. Muốn công bố kết quả `List<String>`, adapter cần kiểm tra từng phần tử và thường tạo bản sao để cách ly alias.

Một API **chủ động ghi `String`** vào đích có thể nhận `List<? super String>`; nhưng API chỉ kiểm tra luồng dữ liệu nên chọn kiểu giúp chặn các thao tác ghi không thuộc trách nhiệm của nó. Khi đọc/ghi một danh sách cụ thể đã có type argument rõ, giữ `List<String>` thay vì raw để compiler bảo vệ invariant.

## 9. Xác thực dữ liệu tại ranh giới: fail fast

Giả sử một API cũ trả về `List`, một endpoint trả về dữ liệu `Object`, hoặc một thư viện chưa cung cấp kiểu generic phù hợp. Nếu không thể sửa ngay nguồn, hãy xác thực dữ liệu **trước** khi công bố nó dưới dạng `List<String>`.

Không nên làm thế này:

```java
// Minh họa cách làm nguy hiểm, không nên dùng:
@SuppressWarnings("unchecked")
static List<String> trustRaw(List raw) {
    return (List<String>) raw;
}
```

Cast `(List<String>) raw` là một cast không thể kiểm tra đầy đủ nội dung generic tại runtime. Nó có thể thành công trên danh sách chứa `Integer` vì erasure chỉ cho JVM kiểm tra đối tượng là một `List`. Annotation `@SuppressWarnings("unchecked")` không sửa dữ liệu hoặc biến cast đó thành kiểm tra thật.

Thay vào đó, xét mẫu xác thực ở phần 4:

```java
static List<String> validatedCopy(List<?> input) {
    List<String> result = new ArrayList<>();
    for (Object element : input) {
        if (!(element instanceof String text)) {
            String found = element == null
                    ? "null" : element.getClass().getSimpleName();
            throw new IllegalArgumentException(
                    "Expected String, found " + found);
        }
        result.add(text);
    }
    return List.copyOf(result);
}
```

Mẫu này là một phương thức trích từ chương trình hoàn chỉnh, cần import `List` và `ArrayList`.

Nó có ba đặc tính có ích:

1. **Xác minh từng phần tử thực** thay vì chỉ cast collection.
2. **Báo lỗi ở ranh giới nhận dữ liệu**, với thông báo chỉ ra kiểu được kỳ vọng và kiểu thực.
3. **Tạo danh sách kết quả mới**, không chia sẻ alias với danh sách đầu vào; biến raw giữ đối tượng đầu vào không thể chèn phần tử vào bản sao sau khi kiểm tra.

Mẫu trên cố ý từ chối `null`. Nếu hợp đồng cho phép null, hãy xác định quy tắc rõ ràng, kiểm tra phù hợp và chọn loại collection kết quả hỗ trợ null (vì `List.copyOf` không chấp nhận null).

Nếu dữ liệu tới từ bên ngoài mà cần trả về một cấu trúc generic nhiều tầng, kiểm tra `instanceof List` chỉ chứng minh được cấu trúc ngoài là `List`, không chứng minh từng phần tử con hoặc mỗi cặp khóa/giá trị đúng kiểu. Cần xác thực **tới mức sâu mà hợp đồng yêu cầu**.

## 10. Dùng `Collections.checkedList` để chặn dữ liệu sai ngay lúc ghi

Java Collections Framework có các wrapper kiểm tra kiểu runtime, ví dụ:

```java
List<String> checked = Collections.checkedList(
        new ArrayList<>(), String.class);
```

Khi một lời gọi đi **qua wrapper `checked`**, wrapper kiểm tra đối tượng được thêm vào bằng `Class<String>`. Trong chương trình:

```java
List rawGuarded = checked;
rawGuarded.add("Safe"); // Thành công.
rawGuarded.add(42);     // ClassCastException tại add qua wrapper.
```

Phần trên là đoạn minh họa, cần import `List`, `ArrayList` và `Collections`. Việc sử dụng raw type để gọi vẫn bị cảnh báo; nhưng checked wrapper bổ sung một lớp phòng vệ runtime, khiến lỗi được phát hiện **gần nơi đưa dữ liệu sai vào**, thay vì kéo dài tới lúc đọc.

Giới hạn quan trọng:

- Wrapper chỉ kiểm tra các thao tác **đi qua wrapper**. Nếu mã khác còn giữ tham chiếu trực tiếp tới backing list và ghi vào đó, wrapper không thể ngăn cách ghi ấy.
- Tạo wrapper quanh một danh sách đã nhiễm phần tử sai **không có nghĩa là xác thực hay làm sạch mọi phần tử có sẵn**.
- Kiểm tra dựa trên `Class<E>` kiểm tra kiểu runtime có thể biểu diễn bằng class token, chẳng hạn `String.class`; nó không thể xác minh sâu kiểu như `List<String>` chỉ bằng một `List.class`.
- Các wrapper checked không thay thế thiết kế generic đúng và cũng không tự biến một collection thành thread-safe.
- Một số collection cho phép `null`; việc chấp nhận null và các ràng buộc dữ liệu khác cần kiểm soát riêng.

Khi bạn kiểm soát được nguồn và tất cả caller, **ưu tiên sửa chữ ký** sang `List<String>` hoặc API thích hợp. Checked wrapper hữu ích như biện pháp bảo vệ bổ sung ở ranh giới với code legacy/khó tin cậy.

## 11. Vì sao `List.of` hoặc `List.copyOf` có thể giúp, và giới hạn của chúng

Một collection không sửa được có thể giảm nguy cơ dữ liệu bị chèn sai **sau khi** tạo:

```java
List<String> cities = List.of("Ha Noi", "Hue");
```

Một alias raw có gọi `add(42)` lên danh sách này cũng không thêm được phần tử: triển khai `List.of` là unmodifiable nên thao tác sửa sẽ ném `UnsupportedOperationException`. Nhưng đây là cơ chế **không cho sửa**, không phải phép xác minh generic của một danh sách bất kỳ.

Trong `validatedCopy`, sau khi kiểm tra từng phần tử, `List.copyOf(result)` tạo danh sách kết quả không sửa được, giúp ngăn một caller khác chèn thêm phần tử vào bản sao đó. Với đầu vào tùy ý, chỉ gọi `List.copyOf(someRawList)` và ép kết quả sang `List<String>` **không chứng minh các phần tử là String**. Nếu collection nguồn đã có dữ liệu sai kiểu, bạn vẫn cần xác thực từng phần tử.

Nếu cần cập nhật danh sách trong nghiệp vụ, một `List<String>` có kiểu đúng và phạm vi chia sẻ/alias được kiểm soát thường hữu ích hơn việc áp đặt bất biến không phù hợp.

## 12. Hướng dẫn xử lý một lỗi `ClassCastException` xuất hiện muộn

Giả sử stack trace báo lỗi tại dòng:

```java
String label = results.get(index);
```

trong khi phần lớn code tin rằng `results` là `List<String>`. Hãy điều tra theo chuỗi nguyên nhân:

1. **Xác định kiểu thật và vị trí phát hiện.** Exception nói kiểu nào không cast được sang kiểu nào? Nếu có `javap`, tìm `checkcast String` sau `get` hoặc `Iterator.next`.
2. **Kiểm tra dữ liệu thực ở ranh giới.** Quan sát kiểu runtime của phần tử bằng tham chiếu `List<?>` và `Object`, tránh cast lại về `String` trong lúc chẩn đoán.
3. **Tìm nơi collection được tạo và truyền đi.** Liệt kê các alias, mapper, repository, cache và API legacy có thể ghi vào cùng đối tượng.
4. **Tìm raw hoặc unchecked gần điểm ghi.** Bật `-Xlint:rawtypes,unchecked`. Chú ý `List raw = typed`, `Map raw = typed`, cast generic không được kiểm tra và hàm trả về raw.
5. **Xác định khoảng cách thời gian.** Lỗi có thể chỉ xuất hiện sau nhiều bước xử lý; đừng kết luận dòng đọc là nơi dữ liệu bị làm sai.
6. **Sửa nguồn vi phạm.** Ưu tiên loại raw type, dùng ràng buộc generic nhất quán và sửa contract phương thức. Nếu dữ liệu từ ngoài, xác thực/copy trước khi đưa vào logic typed.
7. **Thêm kiểm tra hành vi có giá trị.** Kiểm thử ranh giới với giá trị hợp lệ, sai kiểu và null tùy hợp đồng; đảm bảo phát hiện trước khi dữ liệu đi sâu vào hệ thống.

Ví dụ một test không nên chỉ kiểm tra `list.size()` sau khi gọi code legacy: một danh sách có ba phần tử vẫn có thể chứa sai kiểu. Test cần thực sự đọc phần tử theo kiểu kỳ vọng hoặc xác minh dữ liệu ngay tại ranh giới.

### Nhận diện nhanh qua các dấu hiệu

| Dấu hiệu | Khả năng xảy ra | Việc nên kiểm tra |
| --- | --- | --- |
| `ClassCastException` ở `get`/for-each | Cast do compiler chèn khi đọc phần tử | Phần tử runtime tại index đó và mọi alias có quyền ghi. |
| `ClassCastException` ngay tại `add` của checked collection | Wrapper kiểm tra phần tử trước khi ghi | Dữ liệu đầu vào có đúng `Class<E>` của wrapper không. |
| `Unchecked call to add(E)` trên raw `List` | Compiler không xác minh được kiểu phần tử | Thay raw type, hoặc cô lập và xác thực ranh giới legacy. |
| `Unchecked conversion` khi nhận `List` thành `List<String>` | Không có kiểm tra sâu phần tử | Duyệt, xác thực, sao chép trước khi công bố kiểu mới. |
| `ClassCastException` trong service cách xa nơi tạo list | Lỗi phát hiện muộn | Truy luồng ghi/read, trạng thái bị chia sẻ và API trung gian. |

## 13. Những cách sửa sai phổ biến

### Sai lầm A — Giấu cảnh báo bằng `@SuppressWarnings` toàn lớp

`@SuppressWarnings({"rawtypes", "unchecked"})` làm compiler im lặng, nhưng không có tác động tới dữ liệu, phép cast hay hành vi runtime. Dùng annotation này cho cả lớp có thể che giấu thêm những lỗi mới sau này.

Nếu bắt buộc tương tác với API cũ, hãy cô lập chỗ chuyển đổi, kiểm tra được những điều có thể kiểm tra, và giới hạn annotation ở vùng nhỏ nhất kèm lời giải thích chính xác.

### Sai lầm B — Ép kiểu danh sách rồi tin rằng nội dung đã được kiểm tra

`(List<String>) raw` có thể biên dịch với warning nhưng vẫn để dữ liệu sai bên trong. Không dùng cast ấy thay cho vòng lặp xác thực từng phần tử.

### Sai lầm C — Thay raw type bằng `List<Object>` mà không đổi nhu cầu nghiệp vụ

`List<Object>` có nghĩa là danh sách được phép chứa các Object không đồng nhất. Nếu nghiệp vụ yêu cầu toàn `String`, đó là một hợp đồng sai. Nó cũng không phải kiểu nhận được trực tiếp mọi `List<String>` vì generic bất biến.

### Sai lầm D — Cho rằng không ném lỗi ở `add` nghĩa là dữ liệu an toàn

`ArrayList` thông thường không mang ràng buộc String ở runtime. Cảnh báo unchecked tại `add` là tín hiệu cần xử lý dù chưa có exception.

### Sai lầm E — Luôn ép thêm `String.valueOf` khi đọc

`String.valueOf(42)` có thể biến số thành chuỗi `"42"`, nhưng đó là **quy tắc chuyển đổi dữ liệu**, không phải sửa lỗi kiểu theo nghĩa bảo toàn hợp đồng cũ. Nếu nghiệp vụ thực sự cho phép số và chuỗi rồi muốn chuyển thành text, hãy mô hình hóa điều đó rõ ràng. Nếu dữ liệu chỉ được phép là String gốc, chuyển đổi âm thầm có thể che giấu lỗi.

### Sai lầm F — Cứ dùng checked wrapper là dữ liệu bên trong chắc chắn sạch

Wrapper chỉ phòng vệ những thao tác được thực hiện qua nó, không nhất thiết sửa trạng thái trước đó hoặc các alias tới backing collection. Xác thực dữ liệu đã có vẫn là một bước độc lập.

## 14. Bài tập tự kiểm tra

**Bài 1.** Tại sao đoạn sau có thể biên dịch với warning, nhưng lỗi chỉ nổ tại câu lệnh thứ ba?

```java
List<String> items = new ArrayList<>();
List raw = items;
raw.add(100);
String item = items.get(0);
```

**Đáp án:** Raw `List` cho phép lời gọi thêm `Integer` với cảnh báo unchecked. `items.get(0)` trả về đối tượng thực là Integer; tại vị trí yêu cầu String, compiler đã chèn cast sang String và JVM ném `ClassCastException`.

**Bài 2.** `List<?> view = items` có loại bỏ Integer đã bị chèn vào `items` không?

**Đáp án:** Không. Wildcard chỉ thay đổi các thao tác được compiler cho phép qua biến `view`; nó không tạo bản sao và không xác thực nội dung cũ.

**Bài 3.** Với `List<String>` bị nhiễm dữ liệu, gọi `size()` thành công có chứng minh các phần tử đúng kiểu không?

**Đáp án:** Không. `size()` không ép phần tử về String. Lỗi có thể xuất hiện muộn hơn khi đọc cụ thể.

**Bài 4.** Khi nào `Collections.checkedList` giúp fail fast?

**Đáp án:** Khi thao tác thêm phần tử đi qua wrapper. Với wrapper yêu cầu String, thêm Integer bị từ chối ở lần ghi thay vì đợi đến lần đọc qua tham chiếu typed.

**Bài 5.** Có nên sửa bằng `@SuppressWarnings("unchecked")` hoặc cast `(List<String>) raw` không?

**Đáp án:** Không. Chúng không xác minh các phần tử. Cần API generic đúng hoặc xác thực từng phần tử ở ranh giới.

**Bài 6.** Một `Map<String, Integer>` bị raw `Map` chèn giá trị String. Vì sao `containsKey` có thể chạy tốt nhưng `Integer n = map.get(key)` ném lỗi?

**Đáp án:** `containsKey` chỉ kiểm tra khóa, không buộc giá trị trở thành Integer. Lúc `get` trả giá trị Object cho caller yêu cầu Integer, compiler chèn cast và ngoại lệ có thể xảy ra.

## 15. Ghi nhớ

**Nguy cơ lớn nhất của kiểu thô không chỉ là mất tính rõ ràng của chữ ký, mà là có thể phá hợp đồng generic của một đối tượng được chia sẻ, để lỗi phát sinh muộn tại nơi khác.** Lời gọi raw `add` có thể chỉ báo warning và ghi dữ liệu sai; `ClassCastException` xuất hiện khi code typed buộc phải dùng giá trị dưới kiểu kỳ vọng.

Hãy ưu tiên generic đúng trong toàn bộ API, dùng wildcard khi chỉ cần quan sát một kiểu chưa biết, xác thực sâu dữ liệu legacy trước khi gán hợp đồng mạnh hơn, và cân nhắc checked collection ở ranh giới cần phòng vệ runtime. Khi debug, lần theo thứ tự **warning/unchecked write → heap pollution → lần đọc cần cast → ClassCastException** để tìm đúng nguồn vi phạm.
