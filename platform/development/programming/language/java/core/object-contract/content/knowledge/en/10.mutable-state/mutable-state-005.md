# Trường `final` không bảo đảm đối tượng thành phần bất biến trong Java

## 1. Vấn đề: cố định tham chiếu không đồng nghĩa cố định trạng thái

Trong Java, `final` áp dụng cho **biến hoặc trường được khai báo**. Với một trường kiểu tham chiếu, `final` ngăn việc gán lại trường đó sau khi đã khởi tạo hợp lệ; nó **không tự khóa trạng thái** của đối tượng đang được tham chiếu.

Xét ví dụ ngắn:

```java
final StringBuilder text = new StringBuilder("Java");
text.append(" 17");          // Hợp lệ: sửa trạng thái StringBuilder.
// text = new StringBuilder(); // Lỗi biên dịch: không thể gán lại biến final.
System.out.println(text);     // Java 17
```

Đây là **đoạn minh họa** đặt trong một phương thức; dấu chú thích về lỗi biên dịch không phải lệnh chạy. Sau lệnh `append`, chính object `StringBuilder` ban đầu đã đổi nội dung, trong khi biến `text` vẫn trỏ đến object cũ.

Nên phân biệt ba câu hỏi:
1. Có gán lại biến/trường được không? — `final` kiểm soát điều này.
2. Có thay đổi trạng thái của object được tham chiếu không? — phụ thuộc API và thiết kế của object.
3. Có thay đổi trạng thái của **các object con** được tham chiếu từ object đó không? — phụ thuộc cấu trúc lồng nhau, khả năng giữ alias và cách sao chép.

Vấn đề gắn trực tiếp với **Object Contract**: nếu một object dùng dữ liệu từ các thành phần có thể thay đổi để tính `equals()` hoặc `hashCode()`, hai phép này có thể đổi theo thời gian. Khi object đang là phần tử của `HashSet` hoặc khóa của `HashMap`, hậu quả có thể là tra cứu sai hoặc quan hệ trùng lặp thay đổi bất ngờ.

## 2. Những cấp độ bất biến cần phân biệt

| Khái niệm | Ý nghĩa | Điều chưa được bảo đảm |
|---|---|---|
| Biến tham chiếu `final` | Không thể gán một tham chiếu khác cho chính biến đó | Object đang được trỏ tới vẫn có thể mutable |
| Trường `private final` | Không thể gán lại trường sau khi đối tượng được xây dựng hợp lệ bằng Java thông thường | Các thuộc tính của object được tham chiếu vẫn có thể thay đổi |
| Lớp `final` | Không thể tạo subclass của lớp | Các trường hoặc object con vẫn có thể mutable |
| Collection không cho sửa cấu trúc | Không thêm/xóa/thay phần tử thông qua collection đó | Các phần tử mutable bên trong vẫn có thể thay đổi |
| Sao chép nông (shallow copy) | Tạo cấu trúc bên ngoài độc lập, thường giữ các tham chiếu phần tử | Object phần tử được chia sẻ có thể thay đổi |
| Sao chép sâu hoặc snapshot | Sao chép các phần mutable cần bảo vệ theo đồ thị dữ liệu | Cần thiết kế theo mô hình; không có lệnh Java chung tự đóng băng mọi object |
| Bất biến quan sát được (immutable state) | Sau khi tạo, trạng thái có ý nghĩa của object không thay đổi qua API và alias ngoài | Phải kiểm tra getter, constructor, collection, phần tử lồng và cơ chế khác |

Ví dụ:

```java
final List<String> names = new ArrayList<>();
names.add("An");             // Hợp lệ: ArrayList mutable.
names.set(0, "Binh");        // Hợp lệ: thay phần tử.
// names = List.of("Chi");   // Lỗi biên dịch: gán lại biến final.
```

Ở đây biến `names` không đổi tham chiếu nhưng nội dung list có thể đổi. Tương tự, `private final Date createdAt` vẫn có thể bị sửa thông qua `Date.setTime(...)` nếu code giữ tham chiếu đến `Date` hoặc getter trả trực tiếp object đó.

Ngược lại, các đối tượng như `String`, `Instant`, `LocalDate` là các kiểu bất biến trong những cách sử dụng thông thường: nếu một trường `final` tham chiếu trực tiếp tới chúng và không có trạng thái mutable khác ảnh hưởng ngữ nghĩa, lớp bao ngoài dễ giữ bất biến hơn.

## 3. Hai con đường làm rò trạng thái mutable

### 3.1. Alias từ constructor: người gọi giữ tham chiếu ban đầu

Giả sử một lớp như sau:

```java
final class UnsafeTags {
    private final List<String> tags;

    UnsafeTags(List<String> tags) {
        this.tags = tags; // Giữ cùng object List do người gọi truyền vào.
    }
}
```

Tạo `ArrayList` ở bên ngoài rồi truyền vào constructor không tạo bản sao tự động. Người gọi giữ một **alias**, tức một tham chiếu khác đến cùng list. Sau khi object `UnsafeTags` đã được tạo, người gọi vẫn có thể `add`, `remove` hoặc `set`. Trường `tags` tuy `final` nhưng trạng thái object được tham chiếu đã đổi.

Trong ứng dụng thực tế, điều này còn xảy ra với array, `Date`, `Calendar`, `StringBuilder`, `ByteBuffer`, đối tượng chứa collection, hoặc một POJO mutable.

### 3.2. Alias từ getter: lớp tự trả ra đối tượng nội bộ

Ngay cả khi constructor sao chép list, một getter kiểu sau vẫn phá bảo vệ:

```java
List<String> tags() {
    return tags; // Nếu tags là ArrayList nội bộ, caller có thể sửa.
}
```

Nếu đây là list mutable, người gọi có thể dùng `tags().clear()` hoặc `tags().add(...)`. Vì vậy muốn bảo đảm bất biến phải xét **cả đường đưa dữ liệu vào lẫn đường trả dữ liệu ra**.

Một biến thể sai khác là tạo wrapper:

```java
this.tags = Collections.unmodifiableList(input);
```

Wrapper chặn sửa **qua chính wrapper**, nhưng nếu `input` vẫn là `ArrayList` mà caller giữ, caller có thể sửa `input` và wrapper sẽ nhìn thấy thay đổi. Wrapper này là một **view**, không phải snapshot độc lập. Phải kết hợp copy với wrapper khi muốn chặn cả hai hướng:

```java
this.tags = Collections.unmodifiableList(new ArrayList<>(input));
```

Đây là đoạn minh họa trong constructor có biến `input` và trường `tags` tương ứng. Với một danh sách các kiểu bất biến, `List.copyOf(input)` thường ngắn gọn hơn.

## 4. Ví dụ Java 17 độc lập: quan sát sự khác biệt

Tạo file **`FinalReferenceDemo.java`** với nội dung sau. Ví dụ cố ý giữ reference mutable trong `UnsafeTags`; `SafeTags` chụp snapshot bằng `List.copyOf`; `DeepSnapshot` sao chép từng phần tử mutable sang một record bất biến.

```java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public class FinalReferenceDemo {
    public static void main(String[] args) {
        List<String> callerTags = new ArrayList<>(List.of("java"));
        UnsafeTags unsafe = new UnsafeTags(callerTags);

        callerTags.add("hash");
        System.out.println("unsafe after caller edit: " + unsafe.tags());

        unsafe.tags().add("api");
        System.out.println("caller sees getter edit: " + callerTags);

        Set<UnsafeTags> unsafeSet = new HashSet<>();
        unsafeSet.add(unsafe);
        int before = unsafe.hashCode();
        callerTags.add("mutable");
        System.out.println("unsafe hash changed: "
                + (before != unsafe.hashCode()));

        List<String> source = new ArrayList<>(List.of("java"));
        SafeTags safe = new SafeTags(source);
        source.add("hash");
        System.out.println("safe after caller edit: " + safe.tags());

        boolean rejected = false;
        try {
            safe.tags().add("api");
        } catch (UnsupportedOperationException expected) {
            rejected = true;
        }
        System.out.println("safe getter rejects edit: " + rejected);

        Set<SafeTags> safeSet = new HashSet<>();
        safeSet.add(safe);
        int stableHash = safe.hashCode();
        source.clear();
        System.out.println("safe hash stable: "
                + (stableHash == safe.hashCode()));
        System.out.println("safe set contains: " + safeSet.contains(safe));
        System.out.println("same value equals: "
                + safe.equals(new SafeTags(List.of("java"))));

        MutablePart mutablePart = new MutablePart("HN");
        List<MutablePart> shallow = List.copyOf(List.of(mutablePart));
        mutablePart.setLabel("HCM");
        System.out.println("shallow element now: "
                + shallow.get(0).label());

        DeepSnapshot snapshot = new DeepSnapshot(List.of(mutablePart));
        mutablePart.setLabel("Da Nang");
        System.out.println("deep snapshot keeps: "
                + snapshot.parts().get(0).label());
    }

    // CỐ Ý KHÔNG AN TOÀN: final chỉ cố định tham chiếu list.
    static final class UnsafeTags {
        private final List<String> tags;

        UnsafeTags(List<String> tags) {
            this.tags = Objects.requireNonNull(tags, "tags");
        }

        List<String> tags() {
            return tags;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof UnsafeTags that
                    && tags.equals(that.tags);
        }

        @Override
        public int hashCode() {
            return tags.hashCode();
        }
    }

    // Snapshot cấu trúc; an toàn ở đây vì String bất biến.
    static final class SafeTags {
        private final List<String> tags;

        SafeTags(List<String> tags) {
            this.tags = List.copyOf(Objects.requireNonNull(tags, "tags"));
        }

        List<String> tags() {
            return tags;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof SafeTags that
                    && tags.equals(that.tags);
        }

        @Override
        public int hashCode() {
            return tags.hashCode();
        }
    }

    // Đối tượng thành phần cố ý mutable để minh họa alias.
    static final class MutablePart {
        private String label;

        MutablePart(String label) {
            this.label = Objects.requireNonNull(label, "label");
        }

        String label() {
            return label;
        }

        void setLabel(String label) {
            this.label = Objects.requireNonNull(label, "label");
        }
    }

    // Record gồm String bất biến: biểu diễn giá trị snapshot.
    record PartValue(String label) {
        PartValue {
            Objects.requireNonNull(label, "label");
        }
    }

    static final class DeepSnapshot {
        private final List<PartValue> parts;

        DeepSnapshot(List<MutablePart> source) {
            Objects.requireNonNull(source, "source");
            List<PartValue> copied = new ArrayList<>();
            for (MutablePart part : source) {
                copied.add(new PartValue(
                        Objects.requireNonNull(part, "part").label()));
            }
            this.parts = List.copyOf(copied);
        }

        List<PartValue> parts() {
            return parts;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof DeepSnapshot that
                    && parts.equals(that.parts);
        }

        @Override
        public int hashCode() {
            return parts.hashCode();
        }
    }
}
```

Dùng JDK 17 hoặc mới hơn:

```bash
javac --release 17 FinalReferenceDemo.java
java FinalReferenceDemo
```

Kết quả dự kiến:

```text
unsafe after caller edit: [java, hash]
caller sees getter edit: [java, hash, api]
unsafe hash changed: true
safe after caller edit: [java]
safe getter rejects edit: true
safe hash stable: true
safe set contains: true
same value equals: true
shallow element now: HCM
deep snapshot keeps: HCM
```

**Giải thích từng nhóm kết quả:**

- `UnsafeTags` giữ chính `callerTags`; người gọi sửa list sau khi constructor trả về thì `unsafe.tags()` cũng thay đổi. Getter lại trả chính list đó, nên lần sửa qua getter được phản ánh trong `callerTags`.
- `UnsafeTags.hashCode()` dựa trên `List.hashCode()` và nội dung list. Sau khi thêm `"mutable"`, hash trong bộ dữ liệu ví dụ thay đổi mặc dù trường `tags` vẫn là `final`. Đây là mối nguy nếu object đã được đưa vào `HashSet` hoặc làm khóa `HashMap`.
- `SafeTags` dùng `List.copyOf`. Vì các phần tử là `String` bất biến, caller sửa `source` sau constructor không đổi trạng thái bên trong. Danh sách kết quả không hỗ trợ `add`, nên ném `UnsupportedOperationException`. Hash dựa trên nội dung ổn định và `HashSet.contains(safe)` vẫn hoạt động.
- Hai `SafeTags` được tạo từ các list khác nhau nhưng cùng nội dung `["java"]` trả `equals == true`; hash của chúng cũng bằng nhau nhờ cùng thuật toán list.
- `List.copyOf(List.of(mutablePart))` tạo một danh sách không cho sửa cấu trúc nhưng vẫn giữ **tham chiếu cùng `MutablePart`**. Khi gọi `setLabel("HCM")`, phần tử nhìn qua list shallow cũng đổi.
- `DeepSnapshot` chuyển `MutablePart` sang `PartValue` (record chứa một `String` bất biến) và lưu list không cho sửa. Vì thế lần đổi tiếp theo của `mutablePart` sang `"Da Nang"` không đổi dữ liệu đã chụp là `"HCM"`.

**Về kiểm chứng hash collection:** ví dụ in việc hash thay đổi, không dựa vào một kết quả cụ thể của `unsafeSet.contains(unsafe)` sau mutation. Sau khi trường dùng trong hash thay đổi, khả năng lookup không còn được bảo đảm; ở một số cấu hình bucket, truy vấn có thể tình cờ thành công, nên không thể dùng một lần chạy để chứng minh thiết kế an toàn.

## 5. Vì sao vấn đề liên quan trực tiếp đến `equals` và `hashCode`?

Giả sử định nghĩa quan hệ bằng nhau của `UnsafeTags` là `tags.equals(that.tags)`. Khi người gọi thêm hoặc xóa phần tử:
- Giá trị để tính equality thay đổi.
- `hashCode` cũng thay đổi vì list hash phụ thuộc thứ tự và các phần tử.
- Hai object trước đây bằng nhau có thể không còn bằng nhau; hai object trước đây khác nhau cũng có thể trở nên bằng nhau.

Java không cấm một object mutable đổi equality khi trạng thái thay đổi: yêu cầu nhất quán của `equals` phụ thuộc điều kiện thông tin dùng so sánh không đổi. Nhưng việc dùng object đó trong cấu trúc hash có thể phá giả định tra cứu:

1. `HashSet.add(key)` định vị bucket từ hash lúc chèn.
2. Caller thay đổi state ảnh hưởng hash.
3. `HashSet.contains(key)` có thể tìm bucket khác.
4. Object vẫn có thể đang nằm trong tập nhưng thao tác tìm kiếm/loại bỏ không phản ánh kỳ vọng.

Ngay cả khi hash được cố định cố ý, nếu equality của **hai object đã nằm trong Set** thay đổi từ `false` sang `true`, set cũng không tự tái tổ chức và gộp chúng. Vì vậy giải pháp đúng là **ổn định các dữ liệu dùng nhận diện giá trị/khóa trong suốt thời gian lưu trữ**, hoặc không sử dụng object mutable đó trực tiếp làm khóa.

Một số lỗi bổ sung:
- Với mảng, `array.equals(otherArray)` mặc định so **tham chiếu**, không so nội dung; cần `Arrays.equals` và `Arrays.hashCode` (hoặc phiên bản `deepEquals`/`deepHashCode` thích hợp cho mảng lồng nhau).
- Nếu dùng `record` có component là mảng, `equals`/`hashCode` được sinh tự động cho component đó cũng dựa trên equality/hash của tham chiếu mảng, không tự động so sâu nội dung. Record không biến mảng thành bất biến.
- Dùng collection chứa object mutable làm thành phần equality vẫn nguy hiểm dù list không cho thay cấu trúc: list có thể có cùng phần tử trước/sau, nhưng hash của **phần tử** đổi nếu phần tử triển khai hash theo trường mutable.

### Mối quan hệ với `toString()`

Nếu `toString()` đưa nội dung list mutable vào chuỗi hiển thị, hai lần gọi có thể cho hai kết quả khác nhau dù tham chiếu trường là `final`. Đây không nhất thiết là lỗi contract của `toString` vì object thực sự mutable. Tuy nhiên, khi thiết kế value object được kỳ vọng bất biến, log thay đổi bất ngờ là dấu hiệu cần kiểm tra rò rỉ trạng thái.

Không nên dùng `toString` để định nghĩa `equals`, `hashCode` hoặc định danh bền vững.

## 6. Chặn alias để trường `final` thật sự giữ được trạng thái có ý nghĩa

Sau khi phân biệt tham chiếu `final` với object mutable, hãy kiểm tra cả **đầu vào constructor** lẫn **đầu ra getter**. Nếu giữ nguyên `int[]` từ caller, caller sửa mảng là sửa nội bộ; nếu đã copy-in nhưng getter trả chính mảng nội bộ, caller vẫn sửa được trạng thái. Với một mảng primitive một chiều, dùng `clone()` lúc nhận và lúc trả là cách phòng vệ trực tiếp.

```java
// Các dòng minh họa bên trong một class có field byte[] bytes:
this.bytes = input.clone();  // constructor: copy-in
return bytes.clone();        // getter: copy-out
```

Với `List<String>` có phần tử bất biến, `List.copyOf(input)` tạo một danh sách không cho sửa và ổn định về cấu trúc (đồng thời từ chối null). `Collections.unmodifiableList(input)` đơn độc lại là một **view**: sửa `input` qua alias khác vẫn xuất hiện trong view. Nếu phần tử là object mutable, cả `List.copyOf` lẫn bản sao ArrayList đều chỉ sao chép nông; phải chuyển từng phần tử sang kiểu giá trị ổn định nếu trạng thái phần tử tham gia `equals/hashCode`.

Với mảng nhiều chiều, clone mảng ngoài chưa sao chép các hàng; với `Date` hoặc các object mutable khác, cần copy-in/copy-out theo kiểu dữ liệu. Với record, component là `final` nhưng getter tự sinh có thể trả tham chiếu mutable, còn component mảng mặc định so bằng tham chiếu chứ không theo nội dung. Bài *Sao chép phòng vệ để bảo vệ trường mảng hoặc tập hợp* cung cấp ví dụ chạy đầy đủ cho `int[]`, `int[][]`, collection, record, `Arrays.equals/hashCode` và sự khác nhau giữa snapshot và view.

Những bản sao chỉ bảo vệ các đường alias đã kiểm soát; nếu chính class có setter sửa dữ liệu tham gia equality/hash thì object vẫn mutable. `final` và defensive copy cũng không thay cho một chính sách đồng bộ khi bên khác có thể ghi trong lúc chụp snapshot.

## 7. `final`, `record` và bất biến: các hiểu lầm thường gặp

### `final` trên một class

`final class Profile` chỉ chặn kế thừa. Nó vẫn có thể có `private String name` với setter hoặc `private final List<String> tags` trỏ đến `ArrayList` bị sửa từ ngoài. Lớp `final` là một công cụ giúp thiết kế bất biến vì ngăn subclass thêm trạng thái mutable hoặc thay đổi hành vi, nhưng không tự hoàn thành thiết kế.

### Trường `private final`

Giữ trường `private final` giúp giới hạn đường sửa tham chiếu và khiến thiết kế dễ suy luận; nhưng phải kết hợp đối tượng thành phần bất biến, defensive copy và getter không làm rò các tham chiếu mutable. Nếu lưu một `List<MutablePart>` bằng `List.copyOf`, trường và list đều không đổi cấu trúc trong khi từng `MutablePart` vẫn đổi được.

### Record trong Java 17+

Một record tự tạo các trường component `private final`, constructor, accessor, `equals`, `hashCode` và `toString`. Nhưng nó chỉ **nông** về khả năng giữ bất biến:

```java
record Bag(List<String> tags) { }

List<String> original = new ArrayList<>(List.of("x"));
Bag bag = new Bag(original);
original.add("y");
System.out.println(bag.tags()); // [x, y]
```

Đây là đoạn mã minh họa đặt trong phương thức; record nên khai báo trong phạm vi cho phép. Nếu muốn snapshot an toàn cho danh sách `String`, dùng compact constructor:

```java
record SafeBag(List<String> tags) {
    SafeBag {
        tags = List.copyOf(tags);
    }
}
```

Khi chỉ các thành phần trong list là immutable, accessor tự sinh của record trả list không cho sửa nên vẫn giữ trạng thái ổn định. Nhưng nếu record giữ một mảng, getter record sẽ trả cùng tham chiếu mảng; cần tự xử lý defensive copy và chú ý equality/hash của component mảng. Với record có component là object mutable, chỉ dùng `List.copyOf` cũng không đóng băng object con.

### `Collections.unmodifiableList` khác `List.copyOf`

| Biểu thức | Caller sửa list gốc có ảnh hưởng view/kết quả không? | Phần tử mutable có thay đổi được không? |
|---|---|---|
| `Collections.unmodifiableList(original)` | **Có**: wrapper nhìn thay đổi từ original | Có |
| `Collections.unmodifiableList(new ArrayList<>(original))` | Không, với thay đổi cấu trúc ở original | Có |
| `List.copyOf(original)` | Không, với thay đổi cấu trúc ở original | Có |
| `List.of(element)` | Không sửa cấu trúc list | Có, nếu element là object mutable |
| `List.copyOf(original.stream().map(copyToImmutable).toList())` | Không, khi các element snapshot thật sự bất biến | Không qua state đã snapshot |

Tính bất biến của collection và tính bất biến của **từng thành phần** là hai vấn đề riêng.

## 8. Bất biến, an toàn thread và Java Memory Model

`final` còn có ý nghĩa đối với **initialization safety** trong Java Memory Model: nếu object được xây dựng đúng cách (đặc biệt không để `this` thoát khỏi constructor), cơ chế của trường `final` giúp các thread khác thấy giá trị trường đã khởi tạo đúng khi truy cập object được xây dựng. Tuy nhiên:

- `final` không tự bảo đảm mọi phép sửa trạng thái của object được tham chiếu sau constructor được nhìn thấy đồng bộ giữa thread.
- `final List` chứa `ArrayList` có thể bị mutate đồng thời, vẫn phải thiết kế đồng bộ hoặc tránh chia sẻ mutable state.
- Một getter tạo copy tại đúng thời điểm không tự xử lý race nếu nguồn đang bị thread khác sửa song song.
- Các cơ chế như `synchronized`, lock, collection đồng thời hoặc snapshot bất biến xử lý những vấn đề khác nhau, không nên thay thế lẫn nhau.

Một value object có toàn bộ trạng thái có ý nghĩa bất biến sau khởi tạo thường dễ chia sẻ giữa thread hơn vì không cần đồng bộ cho việc **đọc state không đổi**. Nhưng nếu đối tượng có cache lazy mutable hoặc phụ thuộc trạng thái bên ngoài, vẫn cần kiểm tra các đường tương tác ấy.

## 9. Chiến lược thiết kế gắn với Object Contract

Khi muốn object làm **giá trị** hay **khóa của map/set**:
1. Chọn các trường quyết định quan hệ bằng nhau theo ngữ nghĩa miền nghiệp vụ.
2. Xác định những trường đó hoặc các object con có thể thay đổi không.
3. Nếu cần trạng thái ổn định, dùng các giá trị immutable; khi nhận mảng/collection/đối tượng mutable, tạo snapshot bảo vệ thích hợp.
4. Không trả thẳng tham chiếu mutable nội bộ qua getter, callback hay API khác.
5. Triển khai `equals` và `hashCode` dựa trên cùng các thông tin và kiểm tra hash ổn định trong suốt thời gian object được dùng làm khóa.
6. Với một entity **cố ý mutable**, tránh dùng các thuộc tính có thể sửa làm identity dài hạn; cân nhắc ID bất biến hoặc khóa bất biến riêng. Cần phân biệt entity identity với value equality.

**Khi không cần bất biến:** một object mô hình hóa giỏ hàng đang được chỉnh sửa có thể cố ý mutable. Khi đó không nhất thiết phải làm mọi trường bất biến; quan trọng là hiểu rõ hợp đồng, đặt tên API cập nhật rõ ràng, và tránh dùng toàn bộ trạng thái thay đổi làm khóa hash.

### Bẫy về alias sâu

Một kiểu như `final Map<String, List<Item>>` có ít nhất ba tầng:
- Map có thể mutable.
- Các list là giá trị của map có thể mutable.
- Từng `Item` có thể mutable.

Chỉ `Map.copyOf` chặn sửa cấu trúc map, không tự sao chép các list hay item bên trong. Chỉ `List.copyOf` từng list vẫn còn rủi ro `Item`. Muốn snapshot thật sự ổn định phải xác định rồi khóa hoặc copy **mọi thành phần mutable có ảnh hưởng đến equality hoặc hành vi công khai**.

## 10. Lỗi phổ biến và cách nhận diện

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Cho rằng `private final List` là immutable | Caller có thể sửa list qua alias | Defensive copy ở constructor và accessor an toàn |
| Dùng `Collections.unmodifiableList(input)` nhưng giữ `input` bên ngoài | View vẫn phản ánh thay đổi của input | Copy trước khi wrap, hoặc dùng `List.copyOf` |
| Dùng `List.copyOf` cho list phần tử mutable rồi coi là deep immutable | Trạng thái phần tử vẫn thay đổi | Snapshot từng phần tử hoặc dùng kiểu phần tử immutable |
| Getter trả thẳng mảng `byte[]` | Caller sửa mảng nội bộ | `clone()` ở cả constructor lẫn getter |
| Ghi đè `equals` theo nội dung mảng nhưng hash theo địa chỉ mảng | Vi phạm hợp đồng hash | Dùng `Arrays.equals` + `Arrays.hashCode` |
| Dùng collection mutable trong `hashCode` cho object làm khóa | Hash đổi và tra cứu có thể sai | Ổn định nội dung khóa hoặc dùng khóa riêng bất biến |
| Dùng record với component mutable và cho rằng record deep immutable | Accessor làm lộ mutable element/array | Compact constructor và defensive copy theo cấu trúc |
| Dùng `final` để thay đồng bộ luồng | Race và visibility bug khi state con thay đổi | Thiết kế immutable snapshot hoặc đồng bộ rõ ràng |
| Tự gọi `clone` mà không hiểu clone nông/sâu | Alias còn tồn tại ở các object con | Copy constructor/factory có ngữ nghĩa rõ |

## 11. Bài tập tự kiểm tra

### Bài 1 — Dự đoán hành vi của `final`

```java
final List<String> data = new ArrayList<>(List.of("a"));
data.add("b");
// data = new ArrayList<>(); // Không biên dịch nếu bỏ comment.
System.out.println(data);
```

Dự đoán: `[a, b]`. Dòng gán lại chỉ là chú thích để chỉ ra giới hạn của `final`.

### Bài 2 — Snapshot nông và phần tử mutable

Tạo `List<MutablePart>`; chụp `List.copyOf(list)`; sửa `list.get(0).setLabel(...)`. Giải thích vì sao danh sách mới không thể `add` nhưng giá trị `label` nhìn qua danh sách vẫn thay đổi. Sau đó thay phần tử bằng một `record PartValue(String label)` và kiểm tra sự khác biệt.

### Bài 3 — Mảng và object contract

Tạo hai mảng `byte[] a = {1, 2}`, `byte[] b = {1, 2}`. So sánh `a == b`, `a.equals(b)` và `Arrays.equals(a, b)`; dự đoán lần lượt `false`, `false`, `true`. Thiết kế một `ByteKey` không làm lộ mảng nội bộ.

### Bài 4 — Rò trạng thái qua getter

Đổi constructor `UnsafeTags` thành `new ArrayList<>(tags)` nhưng vẫn giữ getter trả trực tiếp list. Có còn thay đổi được object từ bên ngoài không? Có: getter vẫn trả alias đến list mutable nội bộ. Sau đó sửa getter cho trả `List.copyOf(tags)` hoặc dùng trường lưu list snapshot ngay từ constructor và thử lại.

### Bài 5 — Hash collection

Đưa một `UnsafeTags` vào `HashSet` rồi sửa list tham gia `hashCode`. Đọc hash trước và sau, thử tìm lại object. Nếu `contains` trong một lần chạy vẫn trả `true`, giải thích vì sao điều đó **không chứng minh thiết kế đúng**. Thử thêm nhiều phần tử, nhưng không viết test phụ thuộc vào bucket nội bộ của JDK.

### Bài 6 — Chính sách miền nghiệp vụ

Một đơn hàng có ID bất biến và danh sách sản phẩm mutable. Bạn sẽ xác định `equals`/`hashCode` theo ID hay theo danh sách? Nếu nó là **entity**, thường nhận diện theo identity bền vững, không theo những dòng hàng đang sửa. Nếu nó là **value snapshot**, cần snapshot các dòng hàng và bảo đảm chúng có ngữ nghĩa giá trị ổn định. Phải đưa ra quyết định dựa trên ý nghĩa domain thay vì chỉ vì có `final`.

## 12. Checklist hoàn thành

- Phân biệt được “không được gán lại tham chiếu” với “không được sửa object đang được tham chiếu”.
- Nhìn thấy ít nhất hai đường alias: đầu vào constructor và đầu ra getter.
- Biết `List.copyOf` bảo vệ cấu trúc list, còn mutable elements vẫn cần snapshot.
- Biết mảng phải được sao chép phòng vệ ở cả đầu vào và đầu ra nếu cần bất biến.
- Không ngộ nhận class `final` hay Java record là bảo đảm bất biến sâu.
- Giải thích được vì sao việc sửa trường thành phần làm đổi `equals`/`hashCode` và gây rủi ro với `HashSet`/`HashMap`.
- Phân biệt khái niệm immutable với thread-safe; `final` không thay thế đồng bộ của state mutable.
- Biên dịch và chạy được `FinalReferenceDemo.java`, dự đoán đúng stdout và giải thích các kết quả.

**Ý chính:** `final` chỉ cố định việc gán của biến/trường. Muốn một object bất biến về mặt trạng thái và ổn định theo Object Contract, phải thiết kế cả đồ thị tham chiếu có ý nghĩa: kiểm soát alias, sao chép các thành phần mutable cần thiết và không cho dữ liệu tham gia equality/hash biến đổi ngoài dự kiến.