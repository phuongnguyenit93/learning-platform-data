# Enum giữ danh tính từng hằng và không cho ghi đè `equals()` hoặc `hashCode()`

## 1. Kết quả cần hiểu

Trong Java, mỗi **hằng enum** đại diện cho một đối tượng riêng biệt do Java tạo và quản lý. Trong phạm vi một lớp enum đã được nạp, cùng một tên hằng luôn cho lại **chính đối tượng hằng đó**. Vì thế quan hệ bằng nhau của enum là **bằng nhau theo danh tính** (identity equality), không phải tự động so các trường dữ liệu mà hằng mang theo.

Hai điểm cốt lõi:

1. `java.lang.Enum.equals(Object)` được khai báo `final` và chỉ trả `true` khi hai tham chiếu trỏ đến cùng một hằng.
2. `java.lang.Enum.hashCode()` cũng là `final`, cho mã hash gắn với danh tính hằng. Lớp enum do ta khai báo **không thể override** một trong hai phương thức này.

Chính vì vậy, so sánh hai giá trị của **cùng một kiểu enum** bằng `==` là cách thể hiện đơn giản, rõ nghĩa và an toàn về mặt kiểu; `equals()` cũng đúng với hai hằng vì nó dùng cùng nguyên tắc danh tính.

**Phạm vi:** Bài này nói về `enum` của Java, không phải một lớp Java thông thường chỉ định nghĩa các hằng `static final`. Một lớp thường có thể tự override `equals`/`hashCode` theo giá trị; lớp enum thì không thể thay đổi hai phương thức đó.

## 2. Mỗi tên hằng là một thể hiện cố định

Ví dụ:

```java
enum State {
    NEW, RUNNING, DONE
}
```

`State.NEW`, `State.RUNNING` và `State.DONE` là ba đối tượng hằng khác nhau của `State`. Không có cơ chế tạo thêm một hằng `State.NEW` mới bằng `new State()` ở mã ứng dụng. Mỗi lần truy cập `State.NEW`, gọi `State.valueOf("NEW")` hoặc tìm được phần tử `NEW` từ `State.values()`, bạn nhận về cùng tham chiếu hằng trong enum tương ứng.

Các phương thức liên quan:

| API | Ý nghĩa |
| --- | --- |
| `State.NEW` | Truy cập trực tiếp đối tượng hằng `NEW`. |
| `State.valueOf("NEW")` | Trả về đối tượng hằng có **tên khai báo** chính xác `NEW`. |
| `State.values()` | Trả một **mảng mới** chứa tham chiếu tới các đối tượng hằng theo thứ tự khai báo; không tạo đối tượng hằng mới. |
| `state.name()` | Trả tên hằng được khai báo; đây là phương thức `final` của `Enum`. |
| `state.ordinal()` | Vị trí khai báo, bắt đầu từ 0; không phải mã định danh nghiệp vụ bền vững. |
| `state.getDeclaringClass()` | Trả lớp enum khai báo hằng, kể cả với hằng có thân lớp riêng. |

`valueOf` phân biệt chính xác tên, bao gồm chữ hoa và chữ thường; tên không tồn tại gây `IllegalArgumentException`. `name()` và `ordinal()` không thay thế cho danh tính: tên chỉ có ý nghĩa trong **phạm vi kiểu enum**, và thay đổi thứ tự khai báo sẽ thay đổi `ordinal()`.

### “Một thể hiện” trong phạm vi nào?

Mỗi hằng là thể hiện cố định của **kiểu enum ở lần nạp lớp tương ứng**. Không nên diễn giải điều này thành “chỉ có một đối tượng hằng duy nhất trên mọi JVM, mọi tiến trình hoặc mọi class loader”. Java xác định danh tính kiểu theo cả lớp và bộ nạp lớp; các môi trường nạp lớp độc lập không chia sẻ cùng đối tượng hằng trong bộ nhớ.

Trong chương trình Java thông thường, bạn không cần trực tiếp quản lý chi tiết này: `MyEnum.X` và `MyEnum.valueOf("X")` trong cùng kiểu đang dùng trả về cùng hằng.

## 3. `Enum.equals()` là phép so danh tính và có `final`

Logic của `Enum.equals(Object)` tương đương:

```java
public final boolean equals(Object other) {
    return this == other;
}
```

Đây là **mô tả logic** của phương thức có trong `java.lang.Enum`, không phải đoạn mã có thể chép vào một `enum` để override. Từ khóa `final` ngăn override ở tất cả enum cụ thể. Không thể thay đổi nghĩa của `equals()` chỉ vì hằng có thêm thuộc tính hoặc có thân lớp riêng.

So với `Object.equals()` mặc định, tiêu chí danh tính giống nhau; khác biệt thiết kế cần nhớ là `Enum` **chủ động khóa hành vi bằng `final`**. Với lớp thông thường, lập trình viên có thể định nghĩa so giá trị; còn với enum, người dùng chỉ có thể định nghĩa **phương thức so sánh theo ngữ nghĩa khác với tên riêng**, nếu bài toán cần.

Giả sử:

```java
enum Priority {
    LOW(1), MEDIUM(1), HIGH(2);

    private final int weight;

    Priority(int weight) {
        this.weight = weight;
    }

    public int weight() {
        return weight;
    }
}
```

`Priority.LOW.weight()` và `Priority.MEDIUM.weight()` cùng bằng `1`, nhưng:

- `Priority.LOW == Priority.MEDIUM` là `false`;
- `Priority.LOW.equals(Priority.MEDIUM)` cũng là `false`;
- `Priority.LOW.weight() == Priority.MEDIUM.weight()` là `true`.

Hai hằng có cùng thuộc tính không trở thành cùng hằng. **Không được suy từ “cùng dữ liệu” ra “cùng enum”**.

## 4. Vì sao không thể override `equals` và `hashCode`?

Theo định nghĩa của `java.lang.Enum`, cả hai phương thức đều `final`. Java kiểm tra điều này **khi biên dịch**, nên không phải một cảnh báo về phong cách lập trình.

Ví dụ **cố ý sai, không biên dịch**:

```java
enum InvalidStatus {
    A, B;

    @Override
    public boolean equals(Object other) {
        return true;
    }

    @Override
    public int hashCode() {
        return 1;
    }
}
```

Trình biên dịch sẽ từ chối các phương thức override vì `Enum.equals(Object)` và `Enum.hashCode()` đã là `final`. Ngay cả khi cố thay đổi tên tham số, dùng thân lớp riêng cho hằng, hoặc bỏ `@Override`, ta vẫn không được override một phương thức `final` với cùng chữ ký.

Nguyên nhân thiết kế: **danh tính hằng phải là bất biến của kiểu enum**. Nếu lập trình viên tự biến `LOW` và `MEDIUM` thành “bằng nhau” khi cùng `weight`, một phép so sánh kiểu enum sẽ không còn xác định duy nhất hằng nào đang được nói tới. Java giữ một quy tắc nhất quán, được hỗ trợ trong `switch`, `EnumSet`, `EnumMap` và các cơ chế làm việc với hằng enum.

Một enum vẫn có thể cài đặt các phương thức riêng, chẳng hạn `sameWeight(Priority other)`, `hasCode(int code)` hoặc `matches(String input)` để biểu diễn **quan hệ nghiệp vụ bổ sung**. Những phương thức ấy không thay đổi `equals()` của enum.

## 5. `Enum.hashCode()` cũng gắn với danh tính

Hợp đồng chung giữa `equals()` và `hashCode()` trong Java yêu cầu:

```text
a.equals(b) == true  ⇒  a.hashCode() == b.hashCode()
```

Vì hai biến trỏ tới cùng hằng enum luôn trỏ đúng **một đối tượng**, chúng có cùng mã hash. Hai hằng khác nhau luôn không bằng nhau qua `equals`, nhưng **mã hash của chúng vẫn có thể trùng**; mã hash chỉ là một `int` và không phải khóa duy nhất.

Đặc điểm cần nhớ:

- Không thể override `hashCode()` của enum, kể cả khi cần hash theo `weight`, `code` hoặc `name`.
- Giá trị `hashCode()` **không được bảo đảm bằng `ordinal()`, tên hằng, mã nghiệp vụ hoặc địa chỉ bộ nhớ**.
- Không dựa vào con số hash cụ thể để lưu bền vững, truyền giữa tiến trình hay làm ID cố định. Java không cam kết cùng con số hash giữa các lần chạy.
- `System.identityHashCode(enumValue)` cũng dựa trên cơ chế identity; đây không phải cách tạo ID duy nhất tuyệt đối và không thay đổi phép so sánh enum.
- Muốn lấy mã nghiệp vụ ổn định? Định nghĩa trường riêng như `code` và phương thức `code()`, rồi lưu hoặc truyền **mã đã thiết kế**, thay vì `hashCode()`.

Một câu dễ nhầm là “hai hằng enum khác nhau nên hash của chúng chắc chắn khác nhau”. **Sai**: khác danh tính không bảo đảm khác hash. `HashMap` và `HashSet` vẫn cần xử lý collision.

## 6. Ví dụ Java 17+ chạy được

Tạo tệp **`EnumIdentityDemo.java`**:

```java
import java.util.EnumMap;
import java.util.EnumSet;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class EnumIdentityDemo {

    enum Priority {
        LOW(1), MEDIUM(1), HIGH(2);

        private final int weight;

        Priority(int weight) {
            this.weight = weight;
        }

        int weight() {
            return weight;
        }
    }

    enum Other {
        LOW
    }

    public static void main(String[] args) {
        Priority a = Priority.LOW;
        Priority alias = Priority.valueOf("LOW");
        Priority different = Priority.MEDIUM;

        System.out.println("a == alias: " + (a == alias));
        System.out.println("a.equals(alias): " + a.equals(alias));
        System.out.println("a == different: " + (a == different));
        System.out.println("a.equals(different): " + a.equals(different));
        System.out.println("same weight: "
                + (a.weight() == different.weight()));
        System.out.println("same name other type: "
                + a.name().equals(Other.LOW.name()));
        System.out.println("cross enum equals: " + a.equals(Other.LOW));
        System.out.println("same hash for alias: "
                + (a.hashCode() == alias.hashCode()));

        Set<Priority> hashes = new HashSet<>();
        hashes.add(a);
        hashes.add(alias);
        hashes.add(different);
        System.out.println("HashSet size: " + hashes.size());

        EnumMap<Priority, String> names =
                new EnumMap<>(Priority.class);
        names.put(a, "low");
        System.out.println("EnumMap lookup alias: " + names.get(alias));

        EnumSet<Priority> states =
                EnumSet.of(Priority.LOW, Priority.HIGH);
        System.out.println("EnumSet contains alias: "
                + states.contains(alias));

        Priority absent = null;
        System.out.println("null == a: " + (absent == a));
        System.out.println("Objects.equals(null, null): "
                + Objects.equals(null, null));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac EnumIdentityDemo.java
java EnumIdentityDemo
```

Kết quả:

```text
a == alias: true
a.equals(alias): true
a == different: false
a.equals(different): false
same weight: true
same name other type: true
cross enum equals: false
same hash for alias: true
HashSet size: 2
EnumMap lookup alias: low
EnumSet contains alias: true
null == a: false
Objects.equals(null, null): true
```

**Giải thích theo nhóm:**

1. `a` và `alias` là đúng hằng `Priority.LOW`. Lời gọi `valueOf("LOW")` tra hằng hiện hữu chứ không tạo đối tượng mới. Vì thế `==`, `equals` và kết quả `hashCode()` đều nhất quán.
2. `different` là `Priority.MEDIUM`, một hằng khác. Dù `weight` của `LOW` và `MEDIUM` đều bằng `1`, cả `a == different` và `a.equals(different)` đều là `false`.
3. Hai enum `Priority` và `Other` đều có hằng tên `LOW`, nên `name()` của chúng bằng nhau theo chuỗi. Tuy nhiên `a.equals(Other.LOW)` là `false`, vì đó là hai đối tượng hằng từ hai kiểu enum khác nhau.
4. `HashSet` thêm ba tham chiếu `a`, `alias` và `different` nhưng chỉ có **hai đối tượng enum khác nhau**, nên kích thước bằng `2`.
5. `EnumMap` cho phép truy vấn lại giá trị bằng tham chiếu `alias`. `EnumSet` chứa cùng hằng `LOW` nên `contains(alias)` là `true`.
6. `absent == a` kiểm tra an toàn khi `absent` là null. `Objects.equals(null, null)` trả `true` theo quy tắc của tiện ích null-safe; đây không phải phép so sánh hai hằng enum.

Không in hoặc dự đoán con số `a.hashCode()` trong kết quả vì con số này không phải dữ liệu nghiệp vụ ổn định.

## 7. Chọn `==` hay `equals()` khi làm việc với enum

Với hai tham chiếu enum của cùng một kiểu, cả `==` và `equals()` đều trả lời đúng câu hỏi “có phải cùng một hằng hay không?”.

| Tình huống | Khuyến nghị | Lý do |
| --- | --- | --- |
| Hai biến kiểu `Priority` | `a == b` | Diễn đạt trực tiếp identity, an toàn khi một biến null. |
| So với một hằng cụ thể | `status == Priority.LOW` | Ngắn gọn, không có rủi ro `NullPointerException`. |
| Biến có thể null | `status == null` hoặc `status == Priority.LOW` | `==` hỗ trợ null mà không gọi phương thức. |
| Gọi `status.equals(Priority.LOW)` khi status null | Tránh | Gọi phương thức trên null sẽ ném `NullPointerException`. |
| So enum với tham chiếu `Object` bất kỳ | `status.equals(obj)` nếu status khác null, hoặc `Objects.equals(status, obj)` | `equals` nhận `Object` và giữ quy tắc identity. |
| So trường dữ liệu của hai hằng | `a.weight() == b.weight()` hoặc phương thức nghiệp vụ có tên rõ | Đây là quan hệ khác với “cùng hằng”. |

Một lợi ích bổ sung của `==`: khi so hai biểu thức có **kiểu enum cụ thể không tương thích** (ví dụ `Priority.LOW == Other.LOW`), trình biên dịch Java từ chối phép so sánh đó. Trong khi đó `Priority.LOW.equals(Other.LOW)` vẫn biên dịch vì `equals` nhận `Object`, rồi trả `false` khi chạy.

Cũng có thể viết `Priority.LOW.equals(status)` để tránh null ở phía nhận lời gọi; tuy nhiên với enum, `status == Priority.LOW` thường dễ đọc hơn.

### Trường hợp null và `switch`

Một biến enum có thể null vì **biến tham chiếu** có thể null; bản thân hằng enum không phải null. Trong Java 17, dùng `switch` thông thường trên một biến enum null sẽ ném `NullPointerException`. Nếu null mang ý nghĩa nghiệp vụ, kiểm tra null trước khi switch hoặc quy định không chấp nhận null ở biên đầu vào.

## 8. Hằng có trạng thái và thân lớp riêng vẫn giữ identity

Enum có thể khai báo constructor, trường và phương thức:

```java
enum Mode {
    FAST {
        @Override
        String description() {
            return "fast mode";
        }
    },
    SAFE {
        @Override
        String description() {
            return "safe mode";
        }
    };

    abstract String description();
}
```

Đây là đoạn khai báo enum độc lập có thể biên dịch ở cấp package (nếu đặt trong tệp phù hợp, không cần `public`). Hai hằng có thể mang **thân lớp riêng** để override một phương thức do bạn định nghĩa như `description()`. Tuy nhiên, không thể override `Enum.equals()` hoặc `Enum.hashCode()` dù viết code trong thân `FAST` hay `SAFE`, bởi chúng là `final`.

Với enum có thân lớp riêng cho từng hằng, `getClass()` trên hằng có thể trả lớp triển khai riêng cho hằng đó. `getDeclaringClass()` mới là API thích hợp để lấy lớp enum mà hằng thuộc về. Đây là một lý do không tự suy đoán quan hệ bằng nhau từ `getClass()` hay các trường; Java đã khóa identity của enum.

Các trường enum có thể tham chiếu tới cấu trúc mutable nếu lập trình viên thiết kế như vậy. Khi trạng thái nội bộ thay đổi, **danh tính hằng, `equals()` và `hashCode()` vẫn không đổi theo trạng thái ấy**. Dù vậy, vì enum thường được chia sẻ toàn ứng dụng, nên ưu tiên thuộc tính bất biến (`final`, không lộ đối tượng mutable) để tránh lỗi trạng thái và vấn đề luồng.

## 9. Sử dụng enum trong collection và lưu dữ liệu

### `HashSet` / `HashMap`

Enum có `equals`/`hashCode` hợp lệ ngay từ đầu. Dùng enum làm key hoặc phần tử trong các collection dựa trên hash không cần override thêm. Thêm cùng hằng hai lần vào một `HashSet` chỉ tạo một phần tử; hai hằng khác nhau vẫn là các phần tử khác nhau, kể cả khi chúng có cùng thuộc tính.

### `EnumSet` và `EnumMap`

Nếu phần tử/key luôn thuộc **một kiểu enum**, cân nhắc:

- `EnumSet<Priority>`: tập hợp chuyên biệt cho các hằng `Priority`; có thể dùng `EnumSet.of(...)`, `EnumSet.noneOf(Priority.class)`.
- `EnumMap<Priority, V>`: ánh xạ key là các hằng `Priority`; tạo bằng `new EnumMap<>(Priority.class)`.

Hai cấu trúc này tối ưu cho miền hằng enum hữu hạn, sử dụng cấu trúc nội bộ dựa trên các giá trị enum/ordinal. Không cần và không thể định nghĩa hash tùy chỉnh để chúng nhận diện hai hằng có cùng thuộc tính là một.

### Lưu trữ và giao tiếp giữa các hệ thống

Khi cần lưu/truyền giá trị enum, không lưu `hashCode()` hoặc mặc định xem `ordinal()` là ID nghiệp vụ lâu dài. `ordinal()` phụ thuộc thứ tự khai báo, nên thêm hoặc sắp lại hằng có thể thay đổi số thứ tự.

Có thể lưu `name()` nếu hệ thống quy định tên enum là hợp đồng dữ liệu ổn định và quản lý việc đổi tên; hoặc tốt hơn, định nghĩa mã nghiệp vụ tường minh như `"LOW"`, `"MEDIUM"` và phương thức chuyển đổi có kiểm soát. Dù một hằng có mã nghiệp vụ trùng với hằng khác, **identity của chúng vẫn không trùng**.

Khi Java serialize/deserialize enum theo cơ chế chuẩn, giá trị enum được xử lý đặc biệt để khôi phục **hằng được khai báo** theo tên và kiểu, thay vì tạo một bản sao đối tượng enum mới theo cách thông thường. Tuy nhiên, việc hằng có tồn tại và tên có khớp giữa các phiên bản ứng dụng hay không vẫn cần được quản lý.

## 10. Các hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| “Hai hằng có các trường bằng nhau thì `equals()` bằng nhau.” | Sai; `equals()` của enum chỉ dựa trên cùng đối tượng hằng. |
| “Có thể override `equals` hoặc `hashCode` trong enum nếu cần.” | Sai; cả hai phương thức của `Enum` là `final`. |
| “`values()` tạo lại tất cả đối tượng hằng.” | Sai; nó trả mảng mới gồm tham chiếu các hằng sẵn có. |
| “Hai enum khác kiểu nhưng cùng `name()` là bằng nhau.” | Sai; tên giống nhau không biến hai đối tượng thành một. |
| “`ordinal()` chính là `hashCode()`.” | Sai; chúng có mục đích và hợp đồng khác nhau. |
| “Hai hằng khác nhau thì mã hash bắt buộc khác nhau.” | Sai; collision hợp lệ. |
| “Mọi enum chỉ có thể chứa tên hằng, không có dữ liệu hoặc phương thức.” | Sai; enum có constructor, trường, phương thức và thân lớp riêng cho hằng. |
| “Enum không thể được dùng trong `HashMap` khi không override hash.” | Sai; `Enum` đã cung cấp `equals/hashCode` final hợp lệ. |
| “`status.equals(X)` an toàn nếu status null.” | Sai; lời gọi ném `NullPointerException`. Dùng `status == X`. |
| “Nên dùng `hashCode()` của enum làm ID trong database.” | Sai; hash không là định danh nghiệp vụ và không được bảo đảm ổn định qua lần chạy. |

## 11. Khi nào cần so theo giá trị thay vì hằng enum?

Ví dụ, `Priority.LOW` và `Priority.MEDIUM` cùng `weight = 1` nhưng là hai lựa chọn riêng. Nếu chương trình cần gom nhóm theo trọng số, hãy biểu đạt điều ấy **bằng một phép so riêng**:

```java
static boolean hasSameWeight(Priority a, Priority b) {
    if (a == null || b == null) {
        return a == b;
    }
    return a.weight() == b.weight();
}
```

Đây là phương thức minh họa cần đặt trong lớp có truy cập tới enum `Priority` và phương thức `weight()`. Nó cố ý định nghĩa quan hệ **cùng trọng số**, khác với quan hệ **cùng hằng**. Với `a == b == null` về mặt diễn đạt, trường hợp cả hai null được hàm trên coi bằng nhau; tùy nghiệp vụ có thể quy định khác.

Nếu mô hình dữ liệu cần **mỗi giá trị khác nhau là một đối tượng có equality theo dữ liệu**, và các giá trị có thể phát sinh lúc chạy, enum thường không phù hợp. Dùng lớp bất biến hoặc `record` với hợp đồng `equals()`/`hashCode()` theo thành phần, hoặc thiết kế một khóa giá trị riêng. Không cố làm hai hằng enum khác nhau trở thành bằng nhau qua `equals()`.

## 12. Tự kiểm tra

**Câu 1.** Trong enum `Priority { LOW(1), MEDIUM(1) }`, hai hằng có cùng trọng số. `LOW.equals(MEDIUM)` có trả `true` không?

**Đáp án:** Không. Chúng là hai đối tượng hằng riêng, bất kể trường dữ liệu bằng nhau.

**Câu 2.** `Priority.valueOf("LOW") == Priority.LOW` trả gì?

**Đáp án:** `true`. `valueOf` trả hằng enum được khai báo, không tạo bản sao.

**Câu 3.** Vì sao không viết `@Override public int hashCode()` trong enum?

**Đáp án:** `Enum.hashCode()` là `final`; trình biên dịch cấm override.

**Câu 4.** Hai hằng của hai kiểu enum khác nhau đều tên `READY` có bằng nhau qua `equals` không?

**Đáp án:** Không. `name()` có thể giống nhau nhưng đối tượng enum không phải cùng hằng.

**Câu 5.** Khi `status` có thể null, nên dùng `status == State.NEW` hay `status.equals(State.NEW)`?

**Đáp án:** `status == State.NEW`; nó an toàn với null và thể hiện trực tiếp so danh tính enum.

**Câu 6.** Có thể tin rằng `Priority.LOW.hashCode()` luôn giữ một số cố định trên mọi lần chạy JVM không?

**Đáp án:** Không. Chỉ nên dựa vào hợp đồng equality/hash trong quá trình sử dụng bình thường; không coi hash là mã định danh ổn định.

**Ghi nhớ:** Enum có tập hợp hằng hữu hạn và mỗi hằng có **danh tính riêng**. `Enum.equals()` và `Enum.hashCode()` được khai báo **`final`**, nên không thể đổi thành so giá trị. Dùng `==` để nhận diện hằng; khi cần so các thuộc tính, hãy định nghĩa một phép so nghiệp vụ riêng.