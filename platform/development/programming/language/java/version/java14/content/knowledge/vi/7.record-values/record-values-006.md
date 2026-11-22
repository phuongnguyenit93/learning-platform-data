# Tùy biến accessor mà giữ quan hệ nhất quán với constructor của record

Trong Java hiện đại, `record` biểu diễn một tập giá trị bằng các **record components** được khai báo trong phần header. Từ mỗi component, Java tạo một trường `private final` và một phương thức đọc (accessor) mang **đúng tên component**, ví dụ `name()` thay vì mặc định là `getName()`. Bạn có thể **tự viết accessor** để kiểm soát dữ liệu trả ra. Tuy nhiên, accessor và canonical constructor phải cùng diễn đạt một trạng thái hợp lý của record; nếu chúng xử lý dữ liệu theo hai chính sách khác nhau, record có thể đọc ra một giá trị nhưng lại lưu một giá trị khác, dẫn tới kết quả bất ngờ ở `equals()`, `hashCode()`, `toString()` hoặc thao tác sao chép record.

Record trở thành tính năng chính thức từ **Java 16** và tiếp tục được dùng trong các bản Java hiện đại. Mặc dù nội dung nằm trong module Java 14, các ví dụ của bài sử dụng **Java 17+ ổn định**, không dựa vào cú pháp preview cũ.

## 1. Phân biệt component, component field, constructor và accessor

Xét một record đơn giản:

~~~java
record Product(String code, int quantity) {}
~~~

Khi không tự triển khai các thành phần tương ứng, trình biên dịch cung cấp:

- Hai **component fields** kiểu `String` và `int`, mang tên `code` và `quantity`, có tính chất `private final`.
- Canonical constructor tương ứng với chữ ký `Product(String code, int quantity)`.
- Hai accessor công khai `code()` và `quantity()` trả về giá trị các component fields.
- Các phương thức `equals(Object)`, `hashCode()` và `toString()` được dẫn xuất từ **trạng thái các component fields**.

Ví dụ `new Product("A1", 3).code()` trả `"A1"`. Một constructor kiểm tra và chuẩn hóa `code` sẽ quyết định giá trị được **lưu**; accessor quyết định giá trị được **cung cấp cho người gọi**.

| Thành phần | Công việc | Cần giữ nhất quán |
|---|---|---|
| Record header | Công bố tên, kiểu, thứ tự components | Những thông tin này định hình canonical constructor và accessor |
| Canonical constructor | Nhận, kiểm tra, chuẩn hóa và lưu giá trị | Đối tượng tạo thành công phải đạt điều kiện dữ liệu đã cam kết |
| Component field | Giữ dữ liệu thực tế của record | Mọi phép so sánh/mô tả tự sinh dựa trên dữ liệu ở đây |
| Accessor | Cung cấp giá trị component cho người gọi | Không âm thầm diễn đạt thành một giá trị không thể tái tạo cùng trạng thái |
| `equals/hashCode/toString` tự sinh | So sánh, tạo mã băm và mô tả từ component fields | Không được giả định chúng gọi phiên bản accessor do bạn tùy biến |

**Điểm mấu chốt:** Ghi một accessor mới **không thay đổi** cách constructor lưu component. Ngược lại, chuẩn hóa trong constructor không khiến một accessor viết sai tự động trở nên nhất quán.

## 2. “Copy invariant”: quan hệ cần giữ giữa accessor và constructor

Java nêu ra một quy ước quan trọng cho record: nếu đọc tất cả components của một record rồi truyền các giá trị đó vào canonical constructor để tạo record mới, bản mới nên **bằng** bản cũ.

Với record `R` có components `c1`, `c2`, ..., `cn`:

~~~java
R original = /* một R đã tạo thành công */;
R reconstructed = new R(
        original.c1(),
        original.c2()
        // ... các accessor còn lại, đúng thứ tự header
);
boolean consistent = original.equals(reconstructed);
~~~

Đây là **mã giả minh họa quy ước**, không phải chương trình độc lập: `R` và các accessor phải được thay bằng record cụ thể. Điều cần hướng tới là `consistent == true`.

Đối với record một component:

~~~java
record Label(String value) {}

Label a = new Label("java");
Label b = new Label(a.value());
System.out.println(a.equals(b)); // true
~~~

Đoạn trên là minh họa trong một lớp/phương thức có thể thực thi. Bản `b` được tái tạo từ accessor của `a` nên có component field cùng giá trị.

### Vì sao nguyên tắc này quan trọng?

1. Accessor cần trả về thông tin **đủ để tái tạo cùng giá trị record**, theo quy tắc constructor.
2. Constructor phải xác định rõ khi nào chuẩn hóa/validate để đầu vào từ accessor không làm thay đổi ý nghĩa của đối tượng.
3. `equals()` và `hashCode()` tự sinh dùng **component fields**, không lấy kết quả đã biến đổi từ accessor viết tay. Vì vậy accessor che bớt, làm tròn hoặc tự đổi dữ liệu có thể khiến người gọi không tái tạo được record tương đương.
4. Invariant này là **hợp đồng thiết kế**, không phải một phép kiểm tra mà trình biên dịch có thể bảo đảm với mọi accessor/constructor tùy biến.

Khi record chứa các kiểu mutable như `List`, còn phải bảo đảm sự ổn định của dữ liệu giữa hai lần đọc. Chỉ có trường `final` chưa đủ để tự động tạo bất biến sâu.

## 3. Quy tắc khai báo accessor tường minh

Ví dụ tùy biến accessor cho một component `List<String>`:

~~~java
import java.util.ArrayList;
import java.util.List;

record LabelSet(List<String> labels) {
    LabelSet {
        labels = List.copyOf(labels);
    }

    @Override
    public List<String> labels() {
        return new ArrayList<>(labels);
    }
}
~~~

Khi gọi `labels()`, người dùng nhận một **danh sách mới** có nội dung tương đương danh sách lưu trong record. Nó có thể được sửa riêng mà không chạm vào component field của record. Constructor dùng `List.copyOf` để tạo dữ liệu lưu trữ không sửa được; accessor dùng `new ArrayList<>(labels)` khi API muốn trả một **bản sao có thể chỉnh sửa** cho bên gọi.

Một accessor tường minh phải tuân thủ cú pháp theo Java Language Specification:

- Tên **đúng tên component**, không có tham số; ví dụ `labels()`.
- Kiểu trả về **trùng chính xác** kiểu đã khai báo của component, ở đây là `List<String>`; không thay thành `Object` hay một kiểu collection khác.
- Là **phương thức instance `public`**; không được `private`, `protected` hoặc `static`.
- Không có tham số kiểu generic riêng và **không khai báo `throws`**.
- `@Override` được phép đặt trên accessor tường minh của record; nó giúp phát hiện khi tên component thay đổi mà phương thức chưa được cập nhật.

Nếu không cần hành vi đọc đặc biệt, **giữ accessor do Java sinh ra** thường rõ ràng nhất:

~~~java
record Coordinate(int x, int y) {}
~~~

Java đã có `x()` và `y()`. Tự viết `public int x() { return x; }` không đem lại lợi ích nếu chỉ trả lại đúng giá trị.

**Lưu ý về annotation:** Annotations từ component có thể được chuyển sang accessor **tự sinh** khi chúng phù hợp với nơi áp dụng. Nếu bạn tự khai báo accessor, annotations trên component **không tự động được chuyển sang accessor tường minh**. Khi một framework đọc annotation ở phương thức, hãy chủ động xem xét có cần khai báo lại annotation đó hay không.

## 4. Ví dụ đầy đủ Java 17+: accessor trả bản sao nhưng vẫn nhất quán

Tạo tệp **`RecordAccessorDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public class RecordAccessorDemo {

    record LabelSet(String owner, List<String> labels) {
        LabelSet {
            owner = Objects.requireNonNull(owner, "owner").strip();
            if (owner.isEmpty()) {
                throw new IllegalArgumentException("owner is blank");
            }

            labels = List.copyOf(
                    Objects.requireNonNull(labels, "labels")
            );
        }

        @Override
        public List<String> labels() {
            return new ArrayList<>(labels);
        }
    }

    // CỐ Ý THIẾT KẾ SAI để thấy accessor và constructor lệch nhau.
    record BadKey(String value) {
        BadKey {
            Objects.requireNonNull(value, "value");
        }

        @Override
        public String value() {
            return value.strip().toUpperCase(Locale.ROOT);
        }
    }

    // Thiết kế phù hợp: chuẩn hóa trước khi lưu vào component field.
    record GoodKey(String value) {
        GoodKey {
            value = Objects.requireNonNull(value, "value")
                    .strip()
                    .toUpperCase(Locale.ROOT);
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(
                List.of("core", "api")
        );
        LabelSet original = new LabelSet("  An  ", source);

        source.add("outside");
        List<String> returned = original.labels();
        returned.add("local");

        LabelSet reconstructed = new LabelSet(
                original.owner(), original.labels()
        );

        System.out.println("owner=" + original.owner());
        System.out.println("labels=" + original.labels());
        System.out.println("source=" + source);
        System.out.println("returned=" + returned);
        System.out.println(
                "copyEquals=" + original.equals(reconstructed)
        );
        System.out.println(
                "hashEquals=" +
                (original.hashCode() == reconstructed.hashCode())
        );
        System.out.println("record=" + original);

        BadKey bad = new BadKey("ab");
        BadKey badCopy = new BadKey(bad.value());
        System.out.println("badAccessor=" + bad.value());
        System.out.println("badCopyEquals=" + bad.equals(badCopy));
        System.out.println("badStored=" + bad);

        GoodKey good = new GoodKey("  ab  ");
        GoodKey goodCopy = new GoodKey(good.value());
        System.out.println("goodAccessor=" + good.value());
        System.out.println("goodCopyEquals=" + good.equals(goodCopy));
        System.out.println("goodStored=" + good);
    }
}
~~~

Biên dịch và chạy bằng JDK 17 hoặc phiên bản mới hơn hỗ trợ đích Java 17:

~~~bash
javac --release 17 RecordAccessorDemo.java
java RecordAccessorDemo
~~~

**Standard output chính xác:**

~~~text
owner=An
labels=[core, api]
source=[core, api, outside]
returned=[core, api, local]
copyEquals=true
hashEquals=true
record=LabelSet[owner=An, labels=[core, api]]
badAccessor=AB
badCopyEquals=false
badStored=BadKey[value=ab]
goodAccessor=AB
goodCopyEquals=true
goodStored=GoodKey[value=AB]
~~~

### Phân tích đầu vào và kết quả

**Đối với `LabelSet`:**

1. Canonical compact constructor chạy `strip()` trên tham số `owner`, nên lưu `"An"` thay vì `"  An  "`.
2. `List.copyOf(labels)` lấy ảnh chụp danh sách đầu vào; đây là danh sách **không thể sửa đổi qua API List**. Ví dụ dùng phần tử `String` bất biến.
3. Sau khi `original` được tạo, chương trình thêm `"outside"` vào danh sách đầu vào `source`. `original.labels()` vẫn trả `[core, api]` vì record đã lưu một danh sách riêng.
4. Accessor `labels()` tùy biến tạo `new ArrayList<>(labels)` ở **mỗi lần gọi**. Thêm `"local"` vào `returned` không thay đổi dữ liệu lưu trong record.
5. Tạo `reconstructed` từ `original.owner()` và `original.labels()`. Constructor chuẩn hóa owner giống trước và `List.copyOf` lưu lại danh sách có cùng các phần tử. Phép `equals` tự sinh xem hai component fields tương đương nên cho `true`; mã băm của hai record bằng nhau.
6. `toString()` tự sinh hiển thị **các trường lưu trữ**, không dùng chuỗi `source` hay danh sách `returned` mà bên ngoài đã sửa.

**Đối với `BadKey` và `GoodKey`:**

- `BadKey("ab")` **lưu nguyên `"ab"`** vì constructor không chuẩn hóa; accessor lại trả `"AB"`. Bản sao từ accessor lưu `"AB"`, nên `bad.equals(badCopy)` là `false`. `toString()` vẫn cho thấy trường thật là `"ab"`.
- `GoodKey("  ab  ")` chuẩn hóa thành `"AB"` **trong constructor**. Accessor mặc định trả đúng giá trị đã lưu. Tạo bản sao từ `good.value()` vẫn lưu `"AB"`, vì thế hai record bằng nhau.

Mẫu thứ nhất thể hiện **tùy biến accessor có chủ đích nhưng vẫn giữ giá trị logic**. Mẫu thứ hai đối chiếu **biến đổi trạng thái chỉ khi đọc** với **chuẩn hóa khi tạo** để thấy vì sao hai phía cần được thiết kế cùng nhau.

## 5. Thời điểm xử lý trong compact constructor và accessor

Với `LabelSet`, có thể hình dung:

~~~text
new LabelSet("  An  ", source)
  ↓
Các tham số ngầm định owner, labels nhận đầu vào
  ↓
Body compact constructor:
  owner = owner.strip()          → "An"
  validate owner
  labels = List.copyOf(labels)   → danh sách lưu trữ không sửa được
  ↓
Body hoàn tất bình thường
  ↓
Java tự gán component fields final từ các tham số đã xử lý
  ↓
new trả về instance LabelSet đã khởi tạo
  ↓
Gọi accessor:
  owner()  → giá trị field "An" (do Java sinh)
  labels() → new ArrayList<>(field labels) (tự viết)
~~~

Quy tắc thực tế:

- **Constructor** thực hiện validate, normalize và defensive copy **trước khi trạng thái được công bố**.
- **Accessor** cung cấp cách đọc từ trạng thái đã được tạo thành công.
- Nếu cần ngăn đầu vào mutable làm thay đổi record, phải phòng vệ ở **đường vào** (constructor).
- Nếu cần ngăn người nhận sửa trực tiếp đối tượng mutable đang lưu, phải phòng vệ ở **đường ra** (accessor) **hoặc** lưu một đối tượng đã không thể sửa đổi và trả trực tiếp nó.
- Tránh đặt chuẩn hóa có thể ảnh hưởng danh tính giá trị record vào accessor; dữ liệu bên trong và giá trị đọc ra có thể lệch nhau.

Ở compact constructor, các component fields được Java tự gán **sau khi body hoàn tất bình thường** theo thứ tự record header. Không được viết trực tiếp `this.owner = ...` hay `this.labels = ...` trong body compact constructor. Nếu body ném ngoại lệ, việc tạo record thất bại; không có instance hợp lệ được trả về cho bên gọi.

## 6. Tùy biến accessor như thế nào thì còn giữ được tính nhất quán?

### 6.1. Trả về bản sao tương đương về nội dung

Nếu component là `List<String>`, các danh sách khác đối tượng vẫn có thể **bằng nhau theo `List.equals`** khi cùng phần tử theo cùng thứ tự. Vì vậy:

~~~java
@Override
public List<String> labels() {
    return new ArrayList<>(labels);
}
~~~

không tự làm thay đổi nội dung logic khi tái tạo `new LabelSet(owner(), labels())`. Đây chỉ là phần thân accessor minh họa trong record `LabelSet`; không phải một class độc lập.

**Điều kiện:** Phải xét cách so sánh của **kiểu component**, không chỉ xét hình thức hiển thị. Bản sao có cùng hình thức nhưng `equals` của kiểu dữ liệu không coi là bằng nhau thì invariant vẫn có thể bị phá vỡ.

### 6.2. Cần bản sao có thể chỉnh sửa hay một danh sách bất biến?

Nếu mục tiêu chỉ là **không cho bên gọi thay đổi danh sách**, lựa chọn đơn giản hơn:

~~~java
import java.util.List;

record ImmutableLabels(List<String> labels) {
    ImmutableLabels {
        labels = List.copyOf(labels);
    }
}
~~~

Accessor tự sinh `labels()` trả đối tượng danh sách không sửa được đã lưu. Không cần viết thêm accessor nếu trả như vậy đáp ứng API.

Ngược lại, với `LabelSet`, accessor tùy biến chủ động trả một `ArrayList` mới vì **người gọi được phép sửa bản sao của họ** mà không ảnh hưởng record. Đổi lại, mỗi lần gọi phải cấp phát một danh sách mới và sao chép tham chiếu phần tử; cân nhắc hiệu năng khi danh sách lớn hoặc accessor được gọi thường xuyên.

`List.copyOf` là sao chép nông theo các phần tử tham chiếu, không tự deep-copy phần tử mutable. Khi phần tử là `String`, yêu cầu bất biến của ví dụ được đáp ứng. Khi phần tử là đối tượng có trạng thái mutable, cần thiết kế thêm lớp bảo vệ hoặc chọn mô hình giá trị phù hợp.

### 6.3. Không áp dụng máy móc với array

Đặc biệt thận trọng với record có component kiểu mảng:

~~~java
record Bytes(byte[] data) {
    Bytes {
        data = data.clone();
    }

    @Override
    public byte[] data() {
        return data.clone();
    }
}
~~~

Ví dụ này bảo vệ một số đường thay đổi trực tiếp trên mảng, nhưng **không tự động giữ copy invariant với `equals` do Java sinh**: mảng Java dùng `equals` theo **tham chiếu**, nên hai mảng được clone có nội dung giống nhau vẫn không nhất thiết bằng nhau theo `Object.equals`. Cả constructor và accessor đều clone khiến hai record dựng lại từ accessor chứa **hai đối tượng mảng khác nhau**; `equals` mặc định thường cho `false`.

Đừng suy ra rằng “clone” luôn đồng nghĩa với “giữ nguyên giá trị record”. Nếu cần so sánh theo nội dung, hãy cân nhắc một **kiểu value wrapper** có `equals/hashCode` theo nội dung, một `List<Byte>` phù hợp, hoặc thiết kế rõ các phương thức so sánh/biểu diễn và kiểm thử invariant. Nếu phải tự viết `equals/hashCode`, hai phương thức đó cần dùng cùng nguyên tắc và tránh dữ liệu mutable làm mã băm thay đổi sau khi dùng làm khóa.

### 6.4. Accessor hiển thị đã che/mất dữ liệu

Một accessor như:

~~~java
@Override
public String value() {
    return "***";
}
~~~

là **đoạn thân phương thức minh họa**, chỉ có ý nghĩa nếu đặt trong record có component `String value`. Nó làm mất thông tin cần tái tạo bản gốc: xây dựng record mới từ `value()` sẽ lưu `"***"` thay vì giá trị đã lưu. `equals` mặc định vẫn so sánh component fields thật.

Nếu chỉ muốn có **góc nhìn được che/masked**, hãy dùng phương thức **khác tên accessor**:

~~~java
record AccessCode(String code) {
    String maskedCode() {
        return "***";
    }
}
~~~

Với cách này, `code()` do Java sinh vẫn phản ánh dữ liệu lưu, còn `maskedCode()` nói rõ rằng đó là cách hiển thị rút gọn. **Lưu ý bảo mật:** Vì `code()` và `toString()` tự sinh vẫn có thể bộc lộ dữ liệu, không nên sử dụng mẫu record này để lưu bí mật nhạy cảm mà không có chính sách bảo vệ thích hợp. Phương thức hiển thị masked **không phải cơ chế bảo mật**.

## 7. Lỗi thường gặp khi ghép accessor với constructor

| Tình huống | Hậu quả | Cách sửa |
|---|---|---|
| Chuẩn hóa chỉ trong accessor như `BadKey` | Trường lưu nguyên giá trị; accessor trả giá trị khác; sao chép từ accessor có thể `equals == false` | Chuẩn hóa ngay trong canonical constructor |
| Constructor nhận trực tiếp `ArrayList` mutable, accessor trả trực tiếp field | Bên gọi sửa danh sách đầu vào hoặc danh sách được đọc, làm thay đổi trạng thái có thể quan sát | Defensive copy ở constructor; trả dữ liệu không sửa được hoặc bản sao ở accessor |
| Trả `null` hoặc giá trị thay thế cho trạng thái không-null có sẵn | Thông tin đọc ra thiếu; copy invariant không còn bảo đảm | Giữ component theo đúng nghĩa dữ liệu hoặc tạo phương thức hiển thị riêng |
| Đổi kiểu trả về accessor (vd. component `List<String>` nhưng accessor trả `ArrayList<String>`) | Không đáp ứng yêu cầu kiểu trả về **trùng chính xác** component | Khai báo phương thức trả `List<String>` |
| Dùng `private` / `static` / `throws` trên accessor | Sai quy tắc khai báo accessor của record | Dùng `public` instance, không tham số, không `throws` |
| Custom accessor sinh giá trị thay đổi theo thời gian hoặc mỗi lần gọi | Cùng record có thể cho giá trị không ổn định, khó dùng trong sao chép/cache/test | Dùng phương thức có tên khác, tách thuộc tính dẫn xuất khỏi component |
| Tưởng `equals/hashCode/toString` tự sinh gọi accessor tùy biến | Đọc và so sánh mô tả hai “phiên bản” trạng thái khác nhau | Hiểu chúng được dẫn xuất trực tiếp từ component fields |
| Chọn kiểu component là array rồi clone trong accessor | Clone tạo reference mới; mặc định `equals` không so sánh nội dung mảng | Dùng kiểu dữ liệu có value equality hoặc thiết kế lại hợp đồng so sánh |
| Khai báo annotation ở component rồi quên accessor tường minh | Một số framework phản chiếu method không thấy annotation như mong đợi | Kiểm tra nơi framework đọc annotation và gắn lại khi cần |

### Lỗi biên dịch: accessor sai chữ ký

~~~java
// CỐ Ý SAI - ví dụ cho một lỗi, không biên dịch.
record Invalid(String value) {
    @Override
    public Object value() {
        return value;
    }
}
~~~

Kiểu trả về `Object` không khớp `String` của component. Đổi thành `public String value()` hoặc bỏ phương thức để Java sinh accessor đúng.

~~~java
// CỐ Ý SAI - accessor không được có throws clause.
record InvalidThrows(String value) {
    @Override
    public String value() throws Exception {
        return value;
    }
}
~~~

Dù body không ném ngoại lệ, một accessor record tường minh **không được khai báo `throws`**. Hãy loại bỏ `throws`; nếu cần logic có thể thất bại, cân nhắc xử lý cụ thể hoặc thiết kế phương thức nghiệp vụ riêng để không làm accessor mất tính dự đoán.

## 8. Quy trình thiết kế và kiểm thử

**Bước 1 — Xác định giá trị gốc của record.** Record đang lưu mã định danh, một tập nhãn, tọa độ hay trạng thái tổng hợp? Mỗi component có nghĩa gì và kiểu của nó hỗ trợ loại `equals` nào?

**Bước 2 — Chọn chuẩn hóa trong constructor.** Với mã cần `trim`, `strip` hoặc chuẩn hóa chữ hoa/thường, hãy làm trong canonical constructor. Dùng chính sách chuẩn hóa xác định được và phù hợp nghiệp vụ (ví dụ `Locale.ROOT` cho mã không phụ thuộc ngôn ngữ).

**Bước 3 — Chỉ tự viết accessor khi có nhu cầu cụ thể.** Các nhu cầu chính đáng gồm trả bản sao phòng vệ của một thành phần tham chiếu hoặc một representation tương đương theo hợp đồng giá trị. Nếu mặc định đủ dùng, không cần thêm code.

**Bước 4 — Phân biệt “giá trị record” và “dữ liệu trình bày”.** Nếu người dùng cần dạng hiển thị che bớt, rút gọn hoặc format khác, đặt tên riêng như `maskedCode()`, `displayName()` hoặc `summary()`. Accessor gốc nên tiếp tục hỗ trợ tái tạo giá trị.

**Bước 5 — Kiểm tra tính bất biến của dữ liệu tham chiếu.** Với `List`, `Map`, array hoặc object mutable, thử thay đổi dữ liệu nguồn, giá trị trả về và phần tử bên trong. Tùy chọn copy-in/copy-out phải phù hợp kiểu `equals/hashCode` của component.

**Bước 6 — Kiểm tra bất biến copy và hành vi tự sinh.** Tạo một record `a` từ dữ liệu hợp lệ và record `b` từ toàn bộ accessor của `a` theo đúng thứ tự component. Kiểm tra `a.equals(b)` và, khi bằng nhau, `a.hashCode() == b.hashCode()`. Kiểm tra thêm `toString()` để hiểu dữ liệu lưu thật sự và tránh rò rỉ thông tin.

**Bước 7 — Kiểm tra các giá trị biên.** Dùng đầu vào null, chuỗi rỗng/khoảng trắng, danh sách mutable, phần tử null, và các đầu vào dễ thay đổi nghĩa khi chuẩn hóa. Với các component là số thực hoặc array, đặc biệt xem lại quy tắc so sánh.

Một đoạn kiểm tra chung trong phạm vi record `GoodKey`:

~~~java
GoodKey a = new GoodKey("  code  ");
GoodKey b = new GoodKey(a.value());

System.out.println(a.value());            // CODE
System.out.println(a.equals(b));           // true
System.out.println(a.hashCode() == b.hashCode()); // true
~~~

Đây là đoạn sử dụng `GoodKey` đã định nghĩa ở chương trình ví dụ trước, không phải chương trình độc lập.

## 9. Tự kiểm tra

**Câu 1.** Record `BadKey("ab")` lưu `"ab"` nhưng accessor trả `"AB"`. Vì sao `new BadKey(bad.value()).equals(bad)` là `false`?

**Đáp án:** Constructor không chuẩn hóa, nên hai bản lưu hai component fields `"ab"` và `"AB"` khác nhau. `equals` tự sinh so sánh các trường lưu, không so sánh kết quả accessor.

**Câu 2.** Tại sao `LabelSet.labels()` có thể trả một `ArrayList` mới mà bản sao record vẫn bằng bản gốc?

**Đáp án:** Component được khai báo là `List<String>`; danh sách mới giữ cùng các phần tử cùng thứ tự và `List.equals` so sánh theo nội dung. Constructor cũng lưu lại cùng nội dung đó.

**Câu 3.** Chỉ viết `labels = List.copyOf(labels);` trong compact constructor nhưng không tự viết accessor có an toàn không?

**Đáp án:** Với yêu cầu công bố một danh sách không thể sửa đổi có phần tử bất biến phù hợp, có. Accessor tự sinh trả danh sách không sửa được đã lưu; không cần bản sao có thể chỉnh sửa.

**Câu 4.** Vì sao record chứa `byte[]` có thể thất bại ở copy invariant dù đã `clone()` ở constructor và accessor?

**Đáp án:** Các mảng clone là những đối tượng khác tham chiếu. `equals` tự sinh của record sử dụng quy tắc `equals` của component; mảng không so sánh nội dung bằng `Object.equals`.

**Câu 5.** Một accessor có thể khai báo `public ArrayList<String> labels()` khi component là `List<String> labels` không?

**Đáp án:** Không. Với accessor record tường minh, kiểu trả về phải **trùng chính xác** kiểu component `List<String>`; ghi `public List<String> labels()` và có thể trả một đối tượng `ArrayList<String>` trong body.

**Câu 6.** Khi muốn hiển thị mã che bớt, nên sửa `code()` thành trả `"***"` hay tạo `maskedCode()`?

**Đáp án:** Tạo phương thức hiển thị riêng `maskedCode()` để accessor `code()` giữ giá trị component nhất quán với constructor. Với dữ liệu bí mật thật sự, còn cần chính sách bảo mật và phương thức `toString()` an toàn.

## Tài liệu tham khảo

- [Java Language Specification 17, `8.10.3 — Record Members](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.3): điều kiện accessor tường minh, component fields, phương thức `equals/hashCode/toString` tự sinh và copy invariant.
- [Java Language Specification 17, `8.10.4 — Record Constructors](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.4): canonical constructor và compact constructor.
- [Java SE 17 API — `java.lang.Record`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html): hợp đồng của record, constructor, accessor và các phương thức dẫn xuất.
- [OpenJDK JEP 395 — Records](https://openjdk.org/jeps/395): thời điểm record trở thành tính năng chính thức từ Java 16.

**Ghi nhớ:** **Constructor xác lập dữ liệu được lưu; accessor công bố dữ liệu đó.** Khi tùy biến accessor, hãy bảo đảm dữ liệu trả ra vẫn có thể được dùng để dựng lại một record bằng bản gốc, hiểu rằng `equals/hashCode/toString` mặc định dựa trên component fields, và dùng phương thức riêng cho các cách hiển thị làm mất thông tin.