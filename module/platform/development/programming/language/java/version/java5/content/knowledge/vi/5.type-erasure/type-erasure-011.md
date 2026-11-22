# Nhiễm bẩn heap và cảnh báo unchecked

## 1. Heap pollution là sai lệch hợp đồng kiểu, không phải rò rỉ bộ nhớ

**Nhiễm bẩn heap (heap pollution)** là tình trạng một biến có kiểu tham số hóa tham chiếu tới dữ liệu không phù hợp với hợp đồng generic mà kiểu của biến thể hiện.

Ví dụ, mã đang giữ một `List<String>` nhưng thông qua một đường ghi không được kiểm tra đầy đủ, danh sách lại chứa `Integer`. Mã đọc tin rằng phần tử là chuỗi, trong khi đối tượng thực tế là số nguyên.

Khái niệm này khác với:

- Rò rỉ bộ nhớ: dữ liệu không còn cần thiết nhưng vẫn bị giữ tham chiếu.
- Tràn bộ nhớ: chương trình không cấp phát được bộ nhớ cần thiết.
- Hỏng vùng nhớ theo nghĩa ghi tùy tiện vào địa chỉ vật lý.

Vấn đề ở đây là **lời hứa về kiểu bị phá vỡ**. Nó có thể làm một dòng mã đọc bình thường thất bại bằng `ClassCastException` dù dòng đó không chứa phép ép kiểu tường minh.

Cơ chế này vẫn liên quan trực tiếp tới Java hiện nay vì generic sử dụng xóa kiểu. Bài dùng ví dụ chạy trên JDK 17 trở lên. Các đoạn dùng kiểu thô được giữ riêng như **tình huống sai cần nhận biết**, không phải cách thiết kế API nên áp dụng.

Khái niệm chính thức nằm trong [JLS: Variables of Reference Type](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.12.2).

## 2. Vì sao có thể ghi sai mà chưa nổ lỗi ngay?

Trong cách dùng generic thông thường:

```java
List<String> texts = new ArrayList<>();
texts.add("hello");
// texts.add(42); // Khong bien dich
```

Đoạn minh họa cần import `java.util.List` và `java.util.ArrayList`. Trình biên dịch biết `texts` chỉ chấp nhận chuỗi, nên chặn số nguyên.

Nhưng nếu tạo một tham chiếu bằng **kiểu thô (raw type)**:

```java
List<String> texts = new ArrayList<>();
List alias = texts; // raw type
alias.add(42);      // unchecked call
```

`texts` và `alias` cùng trỏ tới một đối tượng danh sách. Kiểu thô làm mất thông tin đối số `String` ở đường ghi.

Đối tượng `ArrayList` thông thường không giữ một token `String` riêng cho mỗi đối tượng `ArrayList<String>` để kiểm tra mọi lần `add`. Sau xóa kiểu, đường gọi này có thể đưa `Integer` vào danh sách.

Đến khi đọc:

```java
String text = texts.get(0);
```

Trình biên dịch đã kiểm tra lời gọi theo `List<String>` và có thể sinh phép kiểm tra ép kiểu sang `String` cho kết quả. Lúc đó, runtime nhìn thấy `Integer` và ném `ClassCastException`.

Dòng thời gian:

```text
List<String> va raw alias cung tro toi mot danh sach
        |
        | raw alias dua Integer vao
        v
Hop dong "phan tu la String" bi pha vo
        |
        | mot noi khac doc nhu String
        v
ClassCastException
```

**Nơi gây sai lệch và nơi báo lỗi có thể cách nhau rất xa.** Chỉ sửa dòng đọc bằng cách thêm một phép ép kiểu khác thường không giải quyết được nguyên nhân.

## 3. Cảnh báo unchecked thực sự nói gì?

**Unchecked** có thể hiểu là “trình biên dịch không thể kiểm tra đầy đủ tính đúng của thao tác theo hợp đồng generic”.

Nó không có nghĩa chắc chắn chương trình sẽ lỗi, nhưng cũng không phải một cảnh báo hình thức có thể bỏ qua tùy ý.

Ví dụ, phép ép:

```java
Object external = List.of(99);
List<String> assumed = (List<String>) external;
```

có thể kiểm tra được đối tượng runtime là một `List`. Nó không kiểm tra và chứng minh toàn bộ phần tử của danh sách là `String`.

Vì vậy, phép ép có thể thành công ngay tại dòng gán rồi lỗi khi đọc phần tử dưới dạng chuỗi. Một phép ép generic không kiểm tra đầy đủ không phải một bước xác thực dữ liệu.

### Các loại cảnh báo cần phân biệt

| Loại thông báo | Tình huống điển hình | Điều cần kiểm tra |
| --- | --- | --- |
| `[rawtypes]` | Dùng `List` thay vì `List<T>` hoặc `List<?>` | Vì sao thông tin kiểu bị bỏ? |
| `[unchecked] unchecked call` | Gọi `add` qua tham chiếu kiểu thô | Giá trị có thể phá hợp đồng kiểu gốc không? |
| `[unchecked] unchecked conversion` | Gán dữ liệu từ kiểu thô sang kiểu có tham số | Có chứng minh được đối số kiểu không? |
| `[unchecked] unchecked cast` | Ép từ `Object` hoặc kiểu rộng sang `List<String>` | Runtime kiểm tra được phần nào? |
| Cảnh báo varargs không reifiable | Tham số như `List<String>...` | Mảng varargs có bị ghi sai hoặc thoát ra ngoài không? |

`rawtypes` và `unchecked` là các nhóm cảnh báo khác nhau. Một phép đọc đơn giản qua kiểu thô không nhất thiết tạo ra đúng cùng cảnh báo với một phép ghi qua kiểu thô.

### Có cảnh báo không đồng nghĩa chắc chắn đã có pollution

Nếu một danh sách thực tế chỉ chứa chuỗi, một phép ép không được kiểm tra đầy đủ có thể vẫn chạy đúng với dữ liệu hiện tại. Tuy nhiên, cảnh báo cho biết bằng chứng kiểu chưa được hệ thống kiểm tra.

Ngược lại, một dòng đọc gây `ClassCastException` có thể không có cảnh báo tại chính dòng đó, vì dữ liệu đã bị làm sai ở nơi khác.

Không nên khẳng định “tệp này không có cảnh báo nên dữ liệu đầu vào chắc chắn an toàn”. Cần xem cả các ranh giới thư viện, những vị trí cảnh báo bị tắt và các đường ghi dùng chung đối tượng.

## 4. Ví dụ đầy đủ: theo dõi từng đường gây lỗi

Chương trình dưới đây cố ý có cảnh báo để quan sát ba nguyên nhân:

- Ghi qua tham chiếu kiểu thô.
- Ép kiểu generic mà không xác thực phần tử.
- Ghi sai vào mảng của tham số varargs kiểu generic.

Nó cũng minh họa một lớp bọc có kiểm tra kiểu khi ghi.

Lưu thành `HeapPollutionDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class HeapPollutionDemo {
    static void rawAlias() {
        List<String> texts = new ArrayList<>();
        List alias = texts;
        alias.add(42);

        Object stored = texts.get(0);
        System.out.println("raw stored class = "
                + stored.getClass().getTypeName());
        try {
            String text = texts.get(0);
            System.out.println(text);
        } catch (ClassCastException exception) {
            System.out.println("raw alias failed on read");
        }
    }

    static void uncheckedCast() {
        Object external = List.of(99);
        List<String> assumed = (List<String>) external;
        System.out.println("unchecked cast accepted");
        try {
            String text = assumed.get(0);
            System.out.println(text);
        } catch (ClassCastException exception) {
            System.out.println("unchecked cast failed on read");
        }
    }

    static void checkedView() {
        List<String> checked = Collections.checkedList(
                new ArrayList<>(), String.class);
        List alias = checked;
        try {
            alias.add(42);
        } catch (ClassCastException exception) {
            System.out.println("checked view rejected write");
        }
        System.out.println("checked size = " + checked.size());
    }

    static void unsafeVarargs(List<String>... rows) {
        Object[] alias = rows;
        alias[0] = List.of(7);
        String text = rows[0].get(0);
        System.out.println(text);
    }

    public static void main(String[] args) {
        rawAlias();
        uncheckedCast();
        checkedView();
        try {
            unsafeVarargs(List.of("safe"));
        } catch (ClassCastException exception) {
            System.out.println("varargs failed on read");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all HeapPollutionDemo.java
java HeapPollutionDemo
```

**Có cảnh báo là kết quả mong đợi của riêng ví dụ lỗi này.** Với `javac` 21, lệnh trên phát ra cảnh báo `rawtypes`, `unchecked call`, `unchecked cast` và cảnh báo generic varargs. Không dùng `-Werror` cho bước tái hiện có chủ đích này.

Stdout của chương trình, không gồm thông báo của trình biên dịch:

```text
raw stored class = java.lang.Integer
raw alias failed on read
unchecked cast accepted
unchecked cast failed on read
checked view rejected write
checked size = 0
varargs failed on read
```

### 4.1. rawAlias: phần tử sai đã nằm trong danh sách

`alias.add(42)` là điểm phá hợp đồng kiểu.

Dòng `Object stored = texts.get(0)` trong ví dụ giữ giá trị dưới dạng `Object` để có thể quan sát lớp thực là `Integer` mà chưa yêu cầu nó phải là `String`.

Đến dòng `String text = texts.get(0)`, giá trị được sử dụng theo hợp đồng chuỗi và lỗi xuất hiện. Điều này giải thích tại sao việc in hoặc đếm phần tử có thể vẫn chạy, trong khi một thao tác đòi đúng kiểu lại thất bại.

### 4.2. uncheckedCast: phép ép thành công không chứng minh phần tử đúng

`external` thực sự là một danh sách số nguyên. Kiểm tra kiểu ngoài là `List` có thể thành công; điều đó không biến các số nguyên thành chuỗi.

Dòng thông báo `unchecked cast accepted` xuất hiện trước lỗi đọc. Cảnh báo giúp nhận biết khoảng trống kiểm tra ngay từ lúc biên dịch.

### 4.3. checkedView: chuyển lỗi về gần đường ghi

`Collections.checkedList(..., String.class)` tạo một cách nhìn có kiểm tra động đối với các thao tác thêm hoặc thay phần tử qua cách nhìn đó.

Khi tham chiếu kiểu thô cố ghi `Integer` qua lớp bọc, nó bị từ chối ngay bằng `ClassCastException`. Danh sách vẫn rỗng.

Đây là công cụ hữu ích để thu hẹp nơi gây sai lệch khi một đối tượng phải đi qua ranh giới chưa có kiểu đầy đủ. Hợp đồng của lớp bọc được mô tả trong [Collections.checkedList](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html#checkedList(java.util.List,java.lang.Class)).

### 4.4. unsafeVarargs: không cần kiểu thô để làm sai mảng generic

`List<String>... rows` được biểu diễn bằng một mảng danh sách trong phương thức.

Mảng có thể được nhìn như `Object[]`. Việc ghi một `List<Integer>` vào một vị trí vẫn phù hợp với kiểu thành phần runtime bên ngoài là `List`, nhưng phá lời hứa rằng từng vị trí là `List<String>`.

Phép ghi `alias[0] = List.of(7)` là điểm làm sai. Đọc số nguyên như chuỗi mới là điểm ném ngoại lệ. Dòng gây sai không nhất thiết có riêng một cảnh báo `unchecked` ngay tại đó; cảnh báo có thể xuất hiện ở khai báo varargs hoặc nơi gọi.

## 5. Cách sửa ưu tiên: giữ thông tin kiểu và kiểm tra dữ liệu tại biên

### 5.1. Dùng generic xuyên suốt đường ghi

Khi sở hữu API, hãy giữ kiểu phần tử:

```java
static void addGreeting(List<String> values) {
    values.add("hello");
}
```

Nếu chỉ cần đọc hoặc quan sát một danh sách chưa biết kiểu phần tử, dùng `List<?>` thay vì bỏ đối số kiểu:

```java
static int count(List<?> values) {
    return values.size();
}
```

`List<?>` không tạo quyền thêm một `Integer` hoặc `String` tùy ý. Nó giữ nguyên ý nghĩa “có một kiểu phần tử chưa biết” và ngăn các phép ghi không được chứng minh.

Nếu phương thức chuyển dữ liệu giữa các cấu trúc, hãy thiết kế quan hệ kiểu rõ ràng bằng tham số kiểu và giới hạn wildcard phù hợp. Đừng nhận kiểu thô rồi ép lại ở bên trong.

### 5.2. Không ép cả danh sách rồi mới hy vọng dữ liệu đúng

Khi nhận `Object` từ một ranh giới chưa có hợp đồng kiểu đầy đủ:

1. Kiểm tra cấu trúc ngoài bằng `instanceof List<?>`.
2. Duyệt từng phần tử.
3. Kiểm tra quy tắc kiểu và quy tắc nghiệp vụ cần thiết.
4. Tạo một tập hợp mới có kiểu đúng.
5. Chọn rõ chính sách đối với `null`.

Việc tạo một bản sao giúp tránh việc một tham chiếu khác tiếp tục sửa danh sách đầu vào sau khi đã kiểm tra.

## 6. Ví dụ đầy đủ: xác thực và tạo snapshot có kiểu

Chương trình dưới đây không có phép ép sang `List<String>` không được kiểm tra. Nó yêu cầu tất cả phần tử là chuỗi khác `null`.

Lưu thành `ValidatedStringsDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class ValidatedStringsDemo {
    static List<String> readStrings(Object external) {
        if (!(external instanceof List<?> values)) {
            throw new IllegalArgumentException("a list is required");
        }

        List<String> copy = new ArrayList<>();
        for (int index = 0; index < values.size(); index++) {
            Object value = values.get(index);
            if (!(value instanceof String text)) {
                throw new IllegalArgumentException(
                        "item " + index + " must be String");
            }
            copy.add(text);
        }
        return List.copyOf(copy);
    }

    public static void main(String[] args) {
        List<Object> external = new ArrayList<>(List.of("An", "Binh"));
        List<String> safe = readStrings(external);
        external.set(0, 42);
        System.out.println("validated snapshot = " + safe);
        System.out.println("external = " + external);

        try {
            readStrings(List.of("An", 42));
        } catch (IllegalArgumentException exception) {
            System.out.println(exception.getMessage());
        }

        try {
            readStrings("not a list");
        } catch (IllegalArgumentException exception) {
            System.out.println(exception.getMessage());
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all -Werror ValidatedStringsDemo.java
java ValidatedStringsDemo
```

Stdout:

```text
validated snapshot = [An, Binh]
external = [42, Binh]
item 1 must be String
a list is required
```

`instanceof String text` vừa kiểm tra kiểu vừa tạo biến `text` có kiểu `String`. Nếu phần tử là `null`, điều kiện không khớp và ví dụ từ chối theo chính sách đã nêu.

Sau xác thực, nguồn `external` bị đổi phần tử đầu thành `42`, nhưng kết quả `safe` vẫn chứa `An` và `Binh` vì có bản sao độc lập về cấu trúc.

Đây là bản sao cấu trúc, không phải một cơ chế sao chép sâu tổng quát cho mọi đối tượng. Trong ví dụ này, phần tử là `String` bất biến nên không có thêm trạng thái phần tử có thể thay đổi cần sao chép.

Phương thức giả định nguồn không bị thay đổi đồng thời trong lúc duyệt. Với dữ liệu chia sẻ giữa luồng, cần một hợp đồng đồng bộ hoặc một ảnh chụp ổn định riêng trước khi xác thực.

### Dữ liệu lồng nhau cần kiểm tra nhiều tầng

Nếu yêu cầu là `List<List<String>>`, kiểm tra mỗi phần tử ngoài là `List<?>` vẫn chưa đủ. Phải kiểm tra tiếp từng phần tử trong mỗi danh sách con.

Một token như `String.class` kiểm tra được chuỗi. Một token `List.class` chỉ chứng minh lớp ngoài là danh sách, không chứng minh các phần tử bên trong là chuỗi.

Hãy coi xác thực kiểu dữ liệu có cấu trúc là một thuật toán rõ ràng, không phải một phép ép kiểu duy nhất.

## 7. Giới hạn của Collections.checkedList

Lớp bọc kiểm tra động hữu ích nhưng có phạm vi cụ thể:

- Các phép ghi cần đi **qua lớp bọc** mới được kiểm tra.
- Nếu giữ một tham chiếu khác tới danh sách nền và ghi trực tiếp qua đó, lớp bọc không chặn được đường đi vòng.
- Việc bọc một danh sách không tương đương với duyệt và xác thực toàn bộ dữ liệu đã có.
- Kiểm tra theo `Class<E>` không tự xác thực nội dung generic lồng nhau.
- Nó không tự tạo tính bất biến hoặc an toàn luồng.

Ví dụ lỗi dùng một danh sách nền mới, rỗng, rồi chỉ đưa lớp bọc ra ngoài. Điều đó làm ranh giới kiểm tra rõ ràng.

Nếu dữ liệu đến từ bên ngoài đã có sẵn phần tử, kiểm tra rồi sao chép thường là cách thiết lập lại hợp đồng tốt hơn việc chỉ bọc và giả định quá khứ đã đúng.

## 8. @SuppressWarnings không sửa dữ liệu

`@SuppressWarnings("unchecked")` yêu cầu trình biên dịch không hiển thị một nhóm cảnh báo tại phạm vi được gắn annotation. Nó:

- Không duyệt phần tử.
- Không đổi lớp thực của đối tượng.
- Không làm một phép ép không được kiểm tra thành phép kiểm tra đầy đủ.
- Không ngăn các tham chiếu khác ghi sai.
- Không chữa heap pollution đã tồn tại.

Chỉ tắt cảnh báo khi có **lập luận độc lập** chứng minh thao tác an toàn trong hợp đồng đang xét, chẳng hạn một cấu trúc nội bộ có các đường ghi được kiểm soát chặt.

Thực hành phù hợp:

1. Ưu tiên thiết kế lại để không cần thao tác unchecked.
2. Nếu vẫn cần, cô lập nó vào phạm vi nhỏ nhất.
3. Ghi rõ quy tắc nào bảo đảm kiểu và ai chịu trách nhiệm giữ quy tắc đó.
4. Kiểm tra các đường ghi, alias và khả năng trả dữ liệu ra ngoài.
5. Chỉ sau đó mới cân nhắc tắt cảnh báo cụ thể.

Không tắt ở mức cả lớp hoặc cả package chỉ để bảng cảnh báo trống. Một vị trí bị tắt quá rộng có thể che các thao tác mới không còn được lập luận cũ bảo vệ.

Cũng không nên dùng `@SuppressWarnings("rawtypes")` cùng `unchecked` như một công thức mặc định. Hai loại cảnh báo phản ánh những thông tin khác nhau cần được kiểm tra.

## 9. @SafeVarargs là lời khẳng định cần chứng minh

`@SafeVarargs` dùng cho một phương thức hoặc constructor varargs đủ điều kiện, để khẳng định phần thân không thực hiện thao tác có thể làm mất an toàn với tham số varargs đó.

Annotation này không tự bảo vệ mảng. Nó không kiểm tra runtime và không biến phương thức `unsafeVarargs` ở ví dụ thành an toàn.

Một tình huống có thể lập luận an toàn là phương thức chỉ đọc các phần tử và đưa chúng vào cấu trúc mới có kiểu đúng:

```java
@SafeVarargs
static <T> List<T> copyValues(T... values) {
    List<T> copy = new ArrayList<>();
    for (T value : values) {
        copy.add(value);
    }
    return copy;
}
```

Đây là phương thức minh họa đặt trong lớp có import `List` và `ArrayList`. Nó không ghi đối tượng khác kiểu vào mảng varargs, không trả mảng ra ngoài và không tạo một alias rộng để nơi khác ghi vào mảng. Kết quả là danh sách mới; bản thân danh sách này vẫn có thể thay đổi.

Đối với phương thức varargs, annotation chỉ được dùng khi phương thức là `static`, `final` hoặc `private`. Constructor varargs cũng có thể thuộc phạm vi áp dụng của annotation. Không đặt nó lên một phương thức thông thường không có tham số varargs.

Quy tắc và ý nghĩa khẳng định được nêu trong [API SafeVarargs](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/SafeVarargs.html).

Nếu không cần giao diện varargs, nhận một `Collection` hoặc `List` có kiểu phù hợp thường tránh được cả vấn đề mảng tham số hóa lẫn nghĩa vụ kiểm tra này.

## 10. Dùng cảnh báo như công cụ tìm nơi mất bằng chứng kiểu

Có thể bật:

```shell
javac --release 17 -Xlint:unchecked -Xlint:rawtypes Example.java
```

Hoặc bật tất cả nhóm kiểm tra phù hợp:

```shell
javac --release 17 -Xlint:all Example.java
```

Với mã dự kiến sạch cảnh báo, thêm `-Werror` để biên dịch thất bại nếu có cảnh báo:

```shell
javac --release 17 -Xlint:all -Werror Example.java
```

`Example.java` ở đây là tên tệp minh họa cho cách dùng lệnh, không phải một chương trình bổ sung.

Ý nghĩa thực tế:

- `-Xlint` mở thông tin chẩn đoán.
- `-Werror` biến cảnh báo thành điều kiện khiến lần biên dịch thất bại.
- Không cờ nào tự chứng minh dữ liệu từ một thư viện chưa kiểm tra hoặc một ranh giới ngoài là đúng kiểu.
- Các annotation tắt cảnh báo vẫn cần được rà soát bằng lập luận về hợp đồng kiểu.

Cách dùng các tùy chọn được mô tả trong [tài liệu javac](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html).

Khi một dòng đọc hợp lệ gây `ClassCastException`, hãy truy ngược tới các điểm mất bằng chứng kiểu: raw alias, unchecked cast/conversion, varargs, dữ liệu ngoài và các vị trí suppression. Đừng chỉ tìm phép ép tại dòng lỗi.

## 11. Những ngộ nhận thường gặp

### “Có ClassCastException nghĩa là có heap pollution”

Không phải mọi `ClassCastException` đều đến từ generic. Ép một `Object` đang chứa số nguyên thành `String` cũng có thể lỗi mà không liên quan tới biến kiểu tham số hóa. Heap pollution là một nguyên nhân cần nhận diện trong bối cảnh generic.

### “List<Object> và List<?> giống raw List”

Không giống nhau.

- `List<Object>` là danh sách có kiểu phần tử `Object`; thêm số hoặc chuỗi phù hợp hợp đồng của nó.
- `List<?>` là danh sách có một kiểu phần tử chưa biết; không tùy ý thêm một giá trị khác `null`.
- Kiểu thô `List` bỏ thông tin đối số kiểu và có thể dẫn tới các thao tác unchecked.

### “Cứ ép kiểu hai lần qua Object là an toàn”

Thêm tầng ép kiểu không bổ sung thông tin mà runtime thiếu. Nó có thể làm compiler chấp nhận một đường đi khác, nhưng không xác thực các phần tử và không sửa dữ liệu.

### “Đổi sang danh sách không cho sửa sẽ làm kiểu đúng”

Ngăn sửa thêm không biến một phần tử `Integer` đã có thành `String`. Phải xác thực nội dung và loại bỏ hoặc từ chối dữ liệu không phù hợp theo hợp đồng.

### “Không đọc phần tử sai thì không có pollution”

Sai lệch hợp đồng có thể tồn tại trước khi được quan sát bằng một phép đọc gây lỗi. Việc một bài kiểm tra chưa chạm tới phần tử đó không chứng minh đường ghi đúng.

## 12. Thực hành tự kiểm tra

### Bài 1: Tìm điểm gây sai

```java
List<String> texts = new ArrayList<>();
List raw = texts;
raw.add(10);
// Nhieu lenh khac...
String text = texts.get(0);
```

**Đáp án:** `raw.add(10)` phá hợp đồng chuỗi; dòng đọc là nơi biểu hiện lỗi. Dòng dùng kiểu thô và lời gọi ghi cần được chẩn đoán, không phải che bằng phép ép ở nơi đọc.

### Bài 2: unchecked cast có xác thực toàn bộ danh sách không?

**Đáp án:** không. Với phép ép sang `List<String>`, runtime có thể kiểm tra cấu trúc ngoài là `List` nhưng không chứng minh từng phần tử là chuỗi. Cần duyệt và xác thực nếu dữ liệu chưa có hợp đồng đáng tin.

### Bài 3: @SuppressWarnings có làm bảy cảnh báo của ví dụ hết nguy hiểm không?

**Đáp án:** không. Nó có thể che thông báo, còn các đường ghi và phép ép trong ví dụ vẫn tạo cùng nguy cơ và vẫn gây các ngoại lệ đã quan sát.

### Bài 4: checkedList có kiểm tra nội dung List<List<String>> sâu không?

**Đáp án:** không tự động. Một kiểm tra lớp ngoài `List.class` không bảo đảm kiểu phần tử ở tầng trong. Cần kiểm tra theo cấu trúc dữ liệu yêu cầu.

### Bài 5: Vì sao bản xác thực tạo danh sách mới?

**Đáp án:** để kết quả không còn phụ thuộc vào đường ghi qua danh sách nguồn sau thời điểm kiểm tra. Nếu chỉ kiểm tra rồi trả lại cùng cấu trúc qua một phép ép unchecked, một alias vẫn có thể làm hợp đồng sai về sau.

Một cảnh báo unchecked chỉ ra nơi hệ thống kiểu không còn kiểm tra được trọn vẹn lời hứa của mã. Công việc cần làm là phục hồi bằng chứng kiểu hoặc dựng một ranh giới xác thực rõ ràng, rồi giữ hợp đồng đó trên mọi đường ghi.
