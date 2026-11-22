# Tái cấu trúc interface, generic và khối đóng tài nguyên trong Java 9+

## 1. Bài toán và mục tiêu

Giả sử một ứng dụng Java phải đọc các dòng dữ liệu từ file, chuyển mỗi dòng thành đối tượng nghiệp vụ và đưa kết quả cho các thành phần khác. Qua nhiều phiên bản, mã nguồn có thể gặp ba vấn đề cùng lúc:

- **Interface phình to:** nhiều `default method` lặp logic đọc và chuyển đổi dòng; nếu đưa các phương thức hỗ trợ thành `public`, chúng vô tình trở thành một phần API mà người dùng thư viện có thể gọi.
- **Generic chưa chặt chẽ:** dùng `List` raw type, ép kiểu ở runtime hoặc chỉ chấp nhận đúng `List<T>` khiến code khó tái sử dụng và thiếu an toàn kiểu dữ liệu.
- **Vòng đời tài nguyên không rõ:** mở `BufferedReader` nhưng quên đóng khi gặp lỗi, hoặc tạo nhiều biến tham chiếu chỉ để ghi `try-with-resources`.

Java 9 bổ sung **private method trong interface**, cho phép dùng **biến tài nguyên đã khai báo và effectively final** trực tiếp trong `try-with-resources`, đồng thời mở rộng **diamond `<>` cho anonymous class** khi kiểu suy luận phù hợp. Kết hợp các khả năng này với generic và wildcard hiện hành, ta có thể cải tổ cùng một bài toán mà không cần raw type hoặc cơ chế đóng file thủ công.

Bài học này là **một thực hành tổng hợp**: xuất phát từ dấu hiệu cần tái cấu trúc, xây dựng thiết kế mới, chạy ví dụ Java hoàn chỉnh, kiểm tra kết quả và giải thích những ranh giới an toàn của từng công cụ.

**Yêu cầu môi trường:** JDK 17+ được khuyến nghị để phát triển hiện nay. Các cú pháp trọng tâm đã có từ Java 9, nên ví dụ chính còn được kiểm tra bằng `javac --release 9`. Không sử dụng API đã lỗi thời hay thư viện bên ngoài.

Sau bài học, bạn sẽ:

1. Phân biệt `abstract`, `default`, `static` và `private` trong interface.
2. Tập trung mã dùng chung vào một private interface helper mà không làm lộ API không cần thiết.
3. Thiết kế `RowParser<T>`, phương thức generic `<T>` và wildcard `? extends T` / `? super T` đúng vai trò.
4. Viết `try (reader)` với biến effectively final, đồng thời xác định ai sở hữu và phải đóng tài nguyên.
5. Hiểu thứ tự đóng và suppressed exception; tránh nuốt exception hoặc đọc lại tài nguyên đã đóng.
6. Kiểm chứng refactor bằng output và bộ test hồi quy, không chỉ dựa vào việc code biên dịch.

## 2. Mô hình trước khi tái cấu trúc

Một thiết kế thường gặp trong mã cần bảo trì có thể như sau:

```java
// Minh họa cấu trúc cần cải tiến, KHÔNG phải file hoàn chỉnh.
interface TextImporter {
    List readAll(BufferedReader in) throws IOException;
    List readDistinct(BufferedReader in) throws IOException;
}
```

Có ba dấu hiệu:

- `List` không mang type argument là **raw type**. Người gọi không biết chắc phần tử là `Item`, `Order` hay `String` và có thể bị `ClassCastException` muộn.
- Hai phương thức cùng phải đọc từng dòng, bỏ dòng rỗng, parse và thêm kết quả. Nếu mỗi chỗ tự viết vòng lặp, dễ khác nhau về xử lý dòng, lỗi và duplicate.
- Tên `in` không cho biết ai sẽ đóng `BufferedReader`. Interface không thể tự bảo đảm xử lý ownership chỉ qua tên tham số.

Nếu trong ứng dụng còn có các đoạn tương tự `open → while(readLine) → parse → close` rải rác, mục tiêu không phải chỉ giảm số dòng: **phải định nghĩa rõ hợp đồng kiểu, kết quả, ngoại lệ và quyền sở hữu tài nguyên**.

### Tiêu chí của bản sau refactor

| Vấn đề | Kết quả mong muốn |
| --- | --- |
| Logic chung bị lặp | Một `private` helper dùng bởi các `default` method |
| API bị lộ helper nội bộ | Helper không thể bị gọi từ code client/implementation |
| `List` raw và ép kiểu | `RowParser<T>`, `List<T>` và hàm `<T>` không có unchecked cast |
| Copy dữ liệu không linh hoạt | Dùng PECS: nguồn `? extends T`, đích `? super T` |
| Đọc file dễ rò rỉ | `try-with-resources` đóng reader kể cả khi parse/lệnh đọc ném exception |
| Dữ liệu trùng lặp | Có chế độ giữ nguyên tất cả hoặc lọc trùng với định nghĩa equality rõ |
| Khó xác minh thay đổi | Test output, hành vi lỗi, thứ tự, resource closure và warning compiler |

Cần giữ nguyên **hành vi nghiệp vụ dự kiến** khi refactor. Trong bài này, mọi dòng có dạng đơn giản `code,count`, dòng trống được bỏ qua, và chế độ distinct loại các dòng có cùng **code và count**. Đây là định nghĩa phục vụ bài tập, **không phải parser CSV tổng quát**.

## 3. Tái cấu trúc interface bằng private method (Java 9)

### 3.1. Vai trò các loại method trong interface

| Loại method | Công dụng | Có là API công khai cho người triển khai/gọi không? |
| --- | --- | --- |
| `T parse(String line);` | Hợp đồng trừu tượng để implementation cung cấp | Có; method trừu tượng của interface thông thường là `public` |
| `default List<T> readAll(...)` | Cung cấp hành vi mặc định có thể được override | Có; method `default` là `public` |
| `static ...` | Utility gắn với tên interface, không cần instance | Có khi khai báo `public static`; gọi qua tên interface |
| `private List<T> collect(...)` | Helper có phần thân, chỉ gọi từ thân interface | **Không**; không được kế thừa/override hoặc gọi trực tiếp từ bên ngoài |
| `private static ...` | Helper tĩnh chỉ dùng nội bộ trong interface | Không; không phụ thuộc instance |

Trong Java 9+, `private` interface method phải có phần thân, không được đồng thời là `abstract` hoặc `default`. Nó hữu ích khi **nhiều default methods cùng cần xử lý giống nhau**, nhưng việc công bố helper ra API chỉ làm tăng gánh nặng tương thích lâu dài.

Ví dụ thiết kế:

```java
interface RowParser<T> {
    T parse(String line);

    default List<T> readAll(BufferedReader reader) throws IOException {
        return collect(reader, false);
    }

    default List<T> readDistinct(BufferedReader reader) throws IOException {
        return collect(reader, true);
    }

    private List<T> collect(BufferedReader reader, boolean distinct)
            throws IOException {
        // Thân dùng chung, triển khai chi tiết ở ví dụ đầy đủ.
        throw new UnsupportedOperationException("illustration only");
    }
}
```

**Đây chỉ là sơ đồ API minh họa**, chưa có import và thân helper thực tế. Phiên bản chạy được nằm ở mục 7. Hai `default` method cung cấp hai thao tác công khai; `collect` là chi tiết triển khai riêng tư của interface.

Lưu ý quan trọng:

- `collect` là **private instance method**, nên có thể gọi `parse(line)` và dùng tham số kiểu `T` của `RowParser<T>`.
- Một `private static` method của interface không thể trực tiếp gọi `parse` vì nó không gắn với một instance, và không thể tham chiếu `T` của interface như một kiểu instance nếu không tự khai báo type parameter.
- Private method không phải một hook mở rộng: implementation không thể override nó. Nếu một phần logic cần tùy biến, hãy đưa phần tùy biến vào method trừu tượng như `parse` hoặc thiết kế một strategy khác.
- Thay đổi từ `public default` helper đã công bố thành `private` có thể phá source/binary compatibility của client. Chỉ ẩn helper vốn là chi tiết nội bộ hoặc chuẩn bị migration phù hợp; **refactor không mặc nhiên đồng nghĩa thay API public**.

### 3.2. Không lạm dụng private helper

Private method đúng chỗ khi đoạn xử lý **chỉ hỗ trợ các method của cùng interface**. Nếu logic có nhiều dependency, state phức tạp hoặc nhiều trách nhiệm I/O độc lập, cân nhắc tách sang một lớp chuyên trách. Không vì Java 9 có private interface methods mà chuyển tất cả service logic vào interface.

Ở ví dụ của bài học, `RowParser<T>` vẫn có **một** nhiệm vụ: từ các dòng ký tự thành danh sách phần tử kiểu `T`. Trách nhiệm **mở/đóng file** nằm ở một phương thức khác để làm rõ ownership.

## 4. Thiết kế generic an toàn: `T`, wildcard và PECS

### 4.1. Interface `RowParser<T>`

```java
interface RowParser<T> {
    T parse(String line);
}
```

`T` là kiểu **một dòng sau khi parse**, ví dụ `Item`. Phương thức `parse` có thể là lambda/method reference nếu chỉ còn một abstract method:

```java
RowParser<Item> parser = Item::fromCsvRow;
```

Đây là **đoạn minh họa**, giả sử lớp `Item` có method `static Item fromCsvRow(String)`. Mặc dù `RowParser<T>` có thêm các `default` và `private` methods ở bản hoàn chỉnh, nó vẫn là **functional interface** vì chỉ có một abstract method. Trong bài chạy, ta dùng anonymous class để minh họa thêm cú pháp Java 9.

### 4.2. Class generic và method generic khác nhau

- `interface RowParser<T>`: `T` thuộc về **mỗi kiểu RowParser** và được dùng trong khai báo `parse`, `readAll`, `readDistinct`.
- `static <T> List<T> load(...)`: `<T>` thuộc về **mỗi lần gọi phương thức load**, compiler thường suy luận được từ `RowParser<T>` truyền vào.
- `List<T>`: danh sách có phần tử kiểu `T`, tránh cast khi đọc ra.
- `List<?>`: danh sách của một kiểu chưa biết; có thể đọc phần tử dưới dạng `Object` nhưng không thể thêm phần tử tùy ý ngoài `null`.
- `List` raw: bỏ thông tin type safety; tránh trong code mới.

```java
// Sơ đồ chữ ký tổng quát.
static <T> List<T> load(Path path, RowParser<T> parser, boolean distinct)
        throws IOException {
    // Thân method thật sẽ mở/đóng reader và gọi parser.
    throw new UnsupportedOperationException("illustration only");
}
```

**Không phải hàm chạy độc lập**. Nó diễn tả rằng `load` tái sử dụng được cho `RowParser<Item>`, `RowParser<Customer>`... mà vẫn giữ danh sách đúng kiểu. Trong code hoàn chỉnh, không cần `Object` hay unchecked cast.

### 4.3. Invariance: `List<Item>` không phải `List<Object>`

Java generic **invariant**. Dù `Item` là subtype của `Object`, gán `List<Item>` vào `List<Object>` là lỗi biên dịch:

```java
List<Item> items = new ArrayList<>();
// List<Object> objects = items;  // LỖI biên dịch: generic invariant.
```

Nếu phép gán được phép, code khác có thể thêm `String` vào `objects`, phá giả định rằng `items` chỉ chứa `Item`. Khi cần **copy** giữa collection có kiểu rộng/hẹp hơn, dùng wildcard có chủ đích thay vì ép kiểu danh sách.

### 4.4. PECS: Producer Extends, Consumer Super

Một hàm copy dùng được cho cả `List<Item> → List<Item>` và `List<Item> → List<Object>`:

```java
static <T> void copyInto(Iterable<? extends T> source,
                         Collection<? super T> target) {
    for (T value : source) {
        target.add(value);
    }
}
```

Đây là đoạn hoàn chỉnh **ở mức method**, cần được đặt trong class và import `java.lang.Iterable` (tự có trong `java.lang`) cùng `java.util.Collection`.

- **`source` là producer:** cung cấp phần tử có kiểu `T` hoặc subtype của `T`, nên dùng `? extends T`. Không giả định có thể thêm `T` bất kỳ vào collection nguồn.
- **`target` là consumer:** nhận `T` hoặc subtype của `T`, nên dùng `? super T`. Khi lấy phần tử từ target, kiểu an toàn chung chỉ là `Object`.
- Không cần `@SuppressWarnings("unchecked")` và không có ép kiểu `(List<Object>)` gây nguy cơ runtime.
- Dùng wildcard khi nó thật sự tăng khả năng tái sử dụng. Với method yêu cầu cùng một kiểu đầu vào/đầu ra chính xác, `T` thường rõ hơn.

### 4.5. Type erasure và equality

Thông tin generic phần lớn được kiểm tra ở **compile time**; không được dựa vào runtime để kiểm tra `instanceof List<Item>`, vì kiểu tham số `Item` đã bị erasure trong biểu diễn runtime. Hãy giữ contract qua API và validation dữ liệu.

Trong bài này, lọc trùng dùng `LinkedHashSet<T>`. Hai đối tượng được coi trùng khi `equals` trả `true` và `hashCode` nhất quán. Chọn `LinkedHashSet` giúp giữ thứ tự xuất hiện đầu tiên. Nếu business định nghĩa “trùng” chỉ theo `code` (bất kể `count`), cần sửa quy tắc đối chiếu hoặc key extraction; **không âm thầm thay nghĩa của distinct**.

## 5. Khối đóng tài nguyên: `try-with-resources` Java 9

### 5.1. Vì sao cần automatic close?

`BufferedReader` giữ nguồn I/O bên dưới (file descriptor/stream). Nếu xử lý lỗi giữa chừng, một `reader.close()` đặt cuối method có thể bị bỏ qua. `try-with-resources` bảo đảm gọi `close()` khi rời block, kể cả khi thân block ném exception.

Cú pháp mở tài nguyên ngay trong `try` đã có từ trước:

```java
try (BufferedReader reader =
         Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    // Dùng reader.
}
```

Đây là **đoạn minh họa**, giả sử `path` được khai báo, import và exception được xử lý.

### 5.2. Java 9: dùng lại biến đã khai báo

Khi một resource **đã được khai báo**, là `final` hoặc **effectively final**, Java 9 cho phép dùng trực tiếp tên biến:

```java
BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8);
try (reader) {
    // Dùng reader; Java tự close khi rời khối.
}
```

**Điều kiện:** `reader` đã được definite assignment, là kiểu `AutoCloseable` và **không bị gán lại** sau khi khởi tạo. Effective final nghĩa là không cần viết từ khóa `final`, nhưng quy tắc gán biến tương đương một biến `final`.

Ví dụ sau **không hợp lệ** vì có gán lại `reader`:

```java
BufferedReader reader = Files.newBufferedReader(firstPath, UTF_8);
reader = Files.newBufferedReader(secondPath, UTF_8);
// try (reader) { ... } // LỖI biên dịch: reader không effectively final.
```

Đây là **anti-example minh họa**, không phải chương trình hợp lệ. Ngoài lỗi biên dịch, phép gán lại còn khiến reader cũ dễ bị bỏ quên không close. Hãy thiết kế một phạm vi quản lý riêng cho mỗi resource hoặc tạo biến mới thay vì đổi tham chiếu.

### 5.3. Ai sở hữu resource?

Trong ví dụ chính:

- `load(Path, parser, ...)` mở `BufferedReader` bằng `Files.newBufferedReader(...)`, nên **load chịu trách nhiệm đóng**.
- `RowParser<T>.readAll(BufferedReader)` chỉ **mượn** reader, đọc và parse; nó **không đóng** reader.
- Khi caller khác trực tiếp gọi `parser.readAll(reader)`, caller đó phải quyết định và bảo đảm vòng đời reader. Không tự ý close tài nguyên do người khác vẫn cần sử dụng, trừ khi API quy định bàn giao ownership rõ ràng.

Hợp đồng này giúp tái sử dụng `RowParser<T>` với reader từ file, network hoặc `StringReader` mà không áp đặt cơ chế mở/đóng cụ thể.

### 5.4. Resource closure và exception

- Các tài nguyên trong `try (a; b)` được đóng theo **thứ tự ngược**: `b` rồi `a`.
- Nếu thân `try` ném lỗi và `close` cũng ném lỗi, exception chính từ thân block được giữ làm **primary**; exception khi close nằm trong `getSuppressed()`.
- Nếu nhiều `close` ném lỗi, Java vẫn cố đóng các resource còn lại và xử lý suppression theo quy tắc try-with-resources.
- Với một resource được mở bằng biến đã có `try (reader)`, **biến vẫn nằm trong scope** sau block nếu scope bao quanh cho phép, nhưng resource đã bị đóng. Đừng cố đọc tiếp.
- `try-with-resources` không tự xử lý mọi lỗi đọc/parse: IOException/unchecked exception vẫn có thể cần catch hoặc truyền lên caller.

Chính sách tốt: khi ghi log lỗi I/O, cân nhắc cả `exception.getSuppressed()` để không mất thông tin về lỗi close. Đừng bắt mọi exception rồi trả một danh sách “thành công” chỉ chứa dữ liệu đã đọc được một nửa.

## 6. Cải tiến thực tế: sơ đồ trách nhiệm

```text
Path (đường dẫn file)
  |
  v
load(Path, RowParser<T>, distinct)        <- chủ sở hữu resource
  | mở Files.newBufferedReader(UTF-8)
  | try (reader)  [Java 9: biến effectively final]
  v
RowParser<T>.readAll / readDistinct       <- public default methods
  |
  v
private RowParser<T>.collect(reader, ...) <- code dùng chung, không lộ API
  | gọi parse(line)                      <- điểm tùy biến type T
  v
List<T>                                   <- kiểu dữ liệu chính xác
  |
  v
copyInto(Iterable<? extends T>,
         Collection<? super T>)           <- tái sử dụng theo PECS
```

**Ranh giới thiết kế:**

1. `RowParser` không phải file service; nó xử lý dòng và trả kết quả.
2. `load` quản lý việc mở/đóng I/O và quyết định gọi chế độ all/distinct.
3. `Item` là đối tượng miền dữ liệu, có quy tắc parse và equality.
4. `copyInto` chỉ sao chép phần tử giữa các collection tương thích, không biết I/O.

Điểm dễ bị bỏ sót khi refactor là **thay đổi ownership tài nguyên**. Nếu trước đây một method trả reader vẫn mở để caller dùng tiếp, chuyển sang `try (reader)` sẽ khiến caller nhận tài nguyên đã đóng. Không áp dụng thay đổi đó mà không sửa lại hợp đồng và kiểm thử.

## 7. Chương trình hoàn chỉnh Java 9+: tích hợp ba kỹ thuật

Đây là chương trình **tự chạy**, không cần dependency bên ngoài. Nó tạo một file tạm chứa ba dòng `A,2`, `B,3`, `A,2`, nạp cả ba, nạp lại với chế độ distinct rồi copy hai đối tượng sang `List<Object>`.

Hai dòng `A,2` trùng nhau theo equality của `Item`. File tạm được xóa trong `finally`; nếu chạy thành công, đường dẫn tạm không ảnh hưởng stdout.

Lưu thành **`RefactorDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public class RefactorDemo {
    interface RowParser<T> {
        T parse(String line);

        default List<T> readAll(BufferedReader reader) throws IOException {
            return collect(reader, false);
        }

        default List<T> readDistinct(BufferedReader reader) throws IOException {
            return collect(reader, true);
        }

        private List<T> collect(BufferedReader reader, boolean distinct)
                throws IOException {
            Objects.requireNonNull(reader, "reader");
            List<T> result = new ArrayList<>();
            Set<T> seen = distinct ? new LinkedHashSet<>() : null;
            String line;
            while ((line = reader.readLine()) != null) {
                if (line.trim().isEmpty()) {
                    continue;
                }
                T value = parse(line);
                if (!distinct || seen.add(value)) {
                    result.add(value);
                }
            }
            return result;
        }
    }

    static final class Item {
        final String code;
        final int count;

        Item(String code, int count) {
            this.code = code;
            this.count = count;
        }

        static Item fromCsvRow(String line) {
            String[] parts = line.split(",", -1);
            if (parts.length != 2 || parts[0].isEmpty()) {
                throw new IllegalArgumentException("Bad row: " + line);
            }
            return new Item(parts[0], Integer.parseInt(parts[1]));
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof Item)) return false;
            Item item = (Item) other;
            return count == item.count && code.equals(item.code);
        }

        @Override
        public int hashCode() {
            return Objects.hash(code, count);
        }

        @Override
        public String toString() {
            return code + ":" + count;
        }
    }

    static <T> List<T> load(Path path, RowParser<T> parser, boolean distinct)
            throws IOException {
        Objects.requireNonNull(parser, "parser");
        BufferedReader reader =
                Files.newBufferedReader(path, StandardCharsets.UTF_8);
        try (reader) {
            return distinct ? parser.readDistinct(reader)
                    : parser.readAll(reader);
        }
    }

    static <T> void copyInto(Iterable<? extends T> source,
                             Collection<? super T> target) {
        for (T item : source) {
            target.add(item);
        }
    }

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("items-", ".txt");
        try {
            Files.write(file, Arrays.asList("A,2", "B,3", "A,2"),
                    StandardCharsets.UTF_8);

            RowParser<Item> parser = new RowParser<>() {
                @Override
                public Item parse(String line) {
                    return Item.fromCsvRow(line);
                }
            };

            List<Item> all = load(file, parser, false);
            List<Item> distinct = load(file, parser, true);

            List<Object> audit = new ArrayList<>();
            copyInto(distinct, audit);

            System.out.println("all=" + all);
            System.out.println("distinct=" + distinct);
            System.out.println("audit=" + audit);
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

### 7.1. Biên dịch và chạy

```bash
javac --release 9 -Xlint:all RefactorDemo.java
java RefactorDemo
```

Dùng JDK 17+ có thể biên dịch target Java 9 bằng `--release 9`. Chương trình đã được kiểm tra với `javac --release 9 -Xlint:all` trên JDK 24: **exit code 0, không có warning**.

**Stdout chính xác**:

```text
all=[A:2, B:3, A:2]
distinct=[A:2, B:3]
audit=[A:2, B:3]
```

Nếu muốn biên dịch theo ngôn ngữ mặc định của JDK đang cài, lệnh `javac RefactorDemo.java` cũng hợp lệ. Trong dự án thực tế, dùng `--release` tương ứng với runtime thấp nhất bạn cam kết hỗ trợ; đừng nhầm version compiler với API có thể chạy trên máy khách.

### 7.2. Giải thích theo bước

**Bước 1 — Interface không bị lộ helper**

`RowParser<T>` chỉ yêu cầu implementation cung cấp `parse(String)`. Hai `default` method `readAll` và `readDistinct` sử dụng cùng `private collect`. Không có mã vòng lặp đọc trùng ở hai public methods. Một class implement `RowParser<Item>` không thể gọi `parser.collect(...)` vì private method không thuộc contract công khai.

**Bước 2 — Typed parser và diamond của Java 9**

`RowParser<Item> parser = new RowParser<>() { ... };` dùng cú pháp diamond `<>` với **anonymous class**. Đây là một cải tiến Java 9 (với điều kiện kiểu được suy luận có thể biểu diễn trong Java, tức denotable type). Ở đây compiler suy luận `T = Item`. Không cần viết `new RowParser<Item>()` ở vế phải hoặc dùng raw `new RowParser()`.

Nếu không cần thân anonymous class, có thể viết ngắn hơn bằng method reference:

```java
RowParser<Item> parser = Item::fromCsvRow;
```

Đây là đoạn minh họa đặt trong `RefactorDemo`, không phải chương trình thứ hai. Việc dùng lambda/method reference không thay đổi contract generic của interface.

**Bước 3 — Private method có thể dùng `T`**

Trong `collect`, `T value = parse(line);` có kiểu chính xác là `Item` với parser đã tạo. Nếu chế độ distinct, `LinkedHashSet<T>` kiểm tra equality của phần tử. `Set` được tạo chỉ khi thực sự cần lọc trùng; khi distinct=false, điều kiện `!distinct` là `true` nên `seen.add` không được gọi.

**Bước 4 — Quản lý file rõ owner**

`load` nhận `Path`, mở `BufferedReader` với `UTF-8` và dùng `try (reader)`. Reader được gán đúng một lần, vì vậy **effectively final**. Mọi lối thoát khỏi block đều gọi `close`, bao gồm khi `readLine`, `parse` hoặc `Integer.parseInt` ném exception. Trách nhiệm đóng tài nguyên không bị đẩy cho `RowParser`.

**Bước 5 — Copy theo PECS**

`List<Item> distinct` là nguồn tương thích với `Iterable<? extends T>`; `List<Object> audit` là đích tương thích với `Collection<? super T>`. Với `T = Item`, compiler cho phép `copyInto(distinct, audit)` mà không phải ép `List<Item>` thành `List<Object>`.

**Bước 6 — File tạm không làm bẩn workspace**

`Files.createTempFile` tạo file tại thư mục tạm của hệ điều hành. `Files.write` ghi đúng ba dòng UTF-8. `finally` gọi `Files.deleteIfExists` để cố gắng dọn file cả khi xảy ra lỗi; resource I/O reader đã được `load` đóng. Ví dụ chỉ có ba dòng để output dễ tái lập.

### 7.3. Giới hạn có chủ đích của parser

`split(",", -1)` chỉ xử lý dữ liệu đơn giản **hai cột không có dấu phẩy trong giá trị**, không hỗ trợ CSV chuẩn có quote/escape/newline trong một field. Nếu import CSV thật từ người dùng, hãy dùng parser CSV phù hợp với định dạng được đặc tả. `fromCsvRow` cũng không kiểm tra số âm, mã chứa whitespace hoặc chính sách giới hạn độ dài; những điều đó phải được xác định theo hợp đồng ứng dụng.

`readDistinct` xác định trùng dựa trên cả `code` và `count`. `A,2` và `A,3` được coi là **khác nhau**. Không thay đổi quy tắc này chỉ vì doanh nghiệp muốn “mỗi mã hàng một dòng” nếu chưa định nghĩa xử lý các bản ghi có số lượng khác nhau.

## 8. Vì sao dùng `try-with-resources` thay cho `finally { close(); }`?

### 8.1. Đường đi khi có lỗi

```text
load(path, parser, distinct)
  |
  | Files.newBufferedReader(...) thành công
  v
try (reader)
  |
  +-- readLine bình thường -> parse -> List<T>
  |
  +-- IOException / lỗi parse -> thoát block
  |
  v
reader.close() được gọi tự động
  |
  +-- nếu close lỗi: xử lý suppressed exception theo đặc tả
  v
trả kết quả hoặc truyền exception
```

`try-with-resources` giúp code có thể chứng minh được rằng tài nguyên đã tạo trong `load` được đóng đúng lúc. Một `finally` viết tay vẫn có thể đóng đúng, nhưng dễ làm mất primary exception, quên điều kiện null, hoặc bỏ sót close khi nhiều tài nguyên liên quan.

Vì `readAll` được thiết kế để mượn reader, nó không nên tự đóng reader ở cuối vòng lặp. Nếu cả hai tầng cùng đóng, code có thể khó suy luận ownership và một số loại resource không cho phép close lặp. Ghi rõ ownership trong tài liệu API.

### 8.2. Hai tài nguyên: đóng theo thứ tự ngược, giữ suppressed exception

Lưu chương trình độc lập sau thành **`CloseDemo.java`**. Nó không cần file thật mà dùng một loại resource giả lập `AutoCloseable`:

```java
import java.io.IOException;

public class CloseDemo {
    static class Resource implements AutoCloseable {
        private final String name;

        Resource(String name) { this.name = name; }

        @Override
        public void close() throws IOException {
            System.out.println("close=" + name);
            if ("second".equals(name)) {
                throw new IOException("close-second");
            }
        }
    }

    public static void main(String[] args) {
        Resource first = new Resource("first");
        Resource second = new Resource("second");
        try (first; second) {
            throw new IOException("body");
        } catch (IOException ex) {
            System.out.println("primary=" + ex.getMessage());
            for (Throwable t : ex.getSuppressed()) {
                System.out.println("suppressed=" + t.getMessage());
            }
        }
    }
}
```

Lệnh:

```bash
javac --release 9 -Xlint:all CloseDemo.java
java CloseDemo
```

**Stdout chính xác đã kiểm tra trên JDK 24:**

```text
close=second
close=first
primary=body
suppressed=close-second
```

Giải thích:

1. Trong `try (first; second)`, Java đóng `second` **trước** `first`.
2. `close` của `second` ném `IOException("close-second")`, nhưng `first.close()` vẫn được gọi.
3. Lỗi chính của body `IOException("body")` được giữ nguyên. Lỗi đóng tài nguyên xuất hiện trong `ex.getSuppressed()`.
4. Nếu chỉ log `ex.getMessage()` và bỏ qua suppressed exceptions, bạn có thể mất bằng chứng cho lỗi cleanup thứ cấp.

Vì biến `first`/`second` được khai báo trước `try` và không bị gán lại, `try (first; second)` dùng cú pháp Java 9. Điều kiện effectively final được compiler kiểm tra tĩnh, không phải chỉ là quy ước code review.

## 9. Kiểm thử refactor và các trường hợp biên

Một bài thực hành refactor được coi là hoàn thành khi **hành vi mới được chứng minh**, không chỉ khi vòng lặp đã được chuyển từ hai method về một private helper.

| Test case | Kết quả kỳ vọng | Lỗi được phát hiện |
| --- | --- | --- |
| Ba dòng `A,2 / B,3 / A,2` với all | Giữ nguyên ba đối tượng theo thứ tự | Đọc sót hoặc đảo thứ tự |
| Cùng dữ liệu với distinct | Còn `A:2, B:3` theo thứ tự đầu tiên | Equality/Set chọn sai |
| Dữ liệu rỗng hoặc chỉ dòng trống | `List<T>` rỗng | Null, lỗi loop hoặc giả định luôn có một dòng |
| Hai dòng `A,2` và `A,3` | Không bị gộp khi equality gồm cả `count` | Nhầm quy tắc duplicate |
| Mã không hợp lệ hoặc số lượng không parse được | Exception rõ ràng; reader vẫn được đóng | Nuốt lỗi / trả partial result |
| `load` với `RowParser<Item>` | Trả `List<Item>`, không raw/unchecked cast | Mất type safety |
| `copyInto(List<Item>, List<Object>)` | Copy thành công, giữ thứ tự | Signature thiếu wildcard |
| Resource từ `load` | Reader được đóng trước khi method trả | Rò rỉ handle khi có lỗi |
| Hai resource trong `try` | Đóng theo thứ tự ngược | Hiểu sai vòng đời |
| Lỗi trong body và lỗi khi close | Lỗi body chính, close lỗi suppressed | Mất nguyên nhân chính |
| `javac --release 9 -Xlint:all` | Biên dịch không warning | Dùng nhầm API mới hơn hoặc raw type |

### 9.1. Một ví dụ JUnit 5 ngắn

Đoạn dưới là **test class cho dự án đã cấu hình JUnit Jupiter**, không có `main` riêng. Đặt trong cùng package với `RefactorDemo` để truy cập nested types không khai báo `private`:

```java
import static org.junit.jupiter.api.Assertions.*;
import java.io.BufferedReader;
import java.io.StringReader;
import java.util.List;
import org.junit.jupiter.api.Test;

class RefactorDemoTest {
    @Test
    void distinctKeepsFirstOccurrence() throws Exception {
        RefactorDemo.RowParser<RefactorDemo.Item> parser =
                RefactorDemo.Item::fromCsvRow;
        try (BufferedReader reader =
                     new BufferedReader(new StringReader("A,2\nB,3\nA,2\n"))) {
            List<RefactorDemo.Item> items = parser.readDistinct(reader);
            assertEquals(2, items.size());
            assertEquals("A:2", items.get(0).toString());
            assertEquals("B:3", items.get(1).toString());
        }
    }

    @Test
    void invalidNumberIsRejected() throws Exception {
        RefactorDemo.RowParser<RefactorDemo.Item> parser =
                RefactorDemo.Item::fromCsvRow;
        try (BufferedReader reader =
                     new BufferedReader(new StringReader("A,not-a-number\n"))) {
            assertThrows(NumberFormatException.class,
                    () -> parser.readAll(reader));
        }
    }
}
```

Bộ test này tập trung vào **hợp đồng dữ liệu** hơn là chi tiết cài đặt của `collect`; private method không cần public chỉ để test. Kiểm tra resource closure thực sự có thể dùng một `Reader` giả lập ghi nhận sự kiện `close()` ở tầng `load`/ownership; không ép test gọi private helper.

### 9.2. Kiểm thử compile-time cũng quan trọng

Generic có nhiều lỗi chỉ compiler mới bắt chính xác: raw type, signature variance, biến không effectively final và cú pháp Java 9. Trong CI, chạy `javac --release 9 -Xlint:all` cho mã đặt mục tiêu Java 9, hoặc cấu hình `--release` theo bản runtime tối thiểu. Đừng chỉ chạy test ở JDK mới nhất mà bỏ kiểm tra target compatibility khi sản phẩm còn hỗ trợ runtime thấp hơn.

**Khi nâng API:** Những thay đổi public method trong interface và thay đổi type parameter có thể ảnh hưởng binary/source compatibility, kể cả khi code implementation trước mắt đã compile. Cần kiểm tra client dự án và module phụ thuộc, không chỉ chính thư viện.

## 10. Các sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm | Cách làm đúng |
| --- | --- | --- |
| Đưa helper thành `default` chỉ để các default methods gọi được | Vô tình thêm public API và tạo khả năng override không mong muốn | Dùng `private` interface method khi helper là chi tiết nội bộ |
| Nghĩ private method có thể override trong implementation | Private method không được kế thừa | Để điểm mở rộng ở method trừu tượng hoặc strategy |
| Viết `private abstract` hoặc `private default` | Không phải tổ hợp modifier hợp lệ | Private interface method phải có body, không là default/abstract |
| Dùng `List` raw type | Mất kiểm tra kiểu, dễ có warning và `ClassCastException` muộn | Khai báo `List<T>` và generic method đúng nghĩa |
| Ép `(List<Object>) someListOfItem` | Bỏ qua invariance, có thể gây heap pollution | Dùng `? extends T` để đọc và `? super T` để ghi |
| Cố thêm `T` tùy ý vào `List<? extends T>` | Không biết subtype thực tế của source | Đọc từ producer, ghi vào consumer phù hợp |
| Quên `equals`/`hashCode` khi lọc trùng | `Set<T>` có thể không nhận diện duplicate nghiệp vụ | Định nghĩa equality hoặc key rõ |
| Dùng `new RowParser()` | Raw anonymous class, mất generic type safety | `new RowParser<>() { ... }` (Java 9+) |
| Gán lại biến trước `try (reader)` | Không effectively final, compiler từ chối | Gán đúng một lần hoặc khai báo resource trực tiếp trong `try` |
| Đóng reader ở cả `load` và `RowParser` | Ownership không rõ, có nguy cơ double-close | Tầng mở resource chịu trách nhiệm đóng |
| Quên đóng khi `parse` ném exception | Rò rỉ handle/file | Bao phạm vi sử dụng trong `try-with-resources` |
| Chỉ ghi log primary exception | Mất thông tin lỗi close | Xem `getSuppressed()` khi chẩn đoán |
| Dùng charset mặc định khi đọc file | Kết quả tùy môi trường | Chỉ rõ `StandardCharsets.UTF_8` hoặc charset giao thức |
| Coi parser minh họa là CSV đầy đủ | Không xử lý quoted fields và dấu phẩy trong dữ liệu | Dùng parser CSV tuân thủ định dạng sản phẩm |
| Biên dịch được nhưng hành vi thứ tự thay đổi | Refactor làm mất tính tương thích nghiệp vụ | Có test all/distinct và duy trì contract thứ tự |

## 11. Quy trình refactor được khuyến nghị

1. **Ghi lại contract hiện tại.** Xác định input format, kết quả, thứ tự, duplicate, xử lý dòng trống, exception, resource ownership và yêu cầu runtime.
2. **Viết test hồi quy trước khi đổi code.** Ít nhất có test cho all/distinct, dữ liệu lỗi, resource closure và generic call-site.
3. **Tách policy khỏi mechanism.** Dùng `parse` làm điểm tùy biến, `private collect` làm mechanism xử lý dòng và `default` methods làm các thao tác công khai.
4. **Giữ type safety.** Thay raw `List`/`Map` bằng generic đúng kiểu; dùng wildcard theo hướng dữ liệu thực tế. Bật `-Xlint:all` và giải quyết warning thay vì ẩn diện rộng.
5. **Chốt ownership.** Ai mở resource là người đóng, trừ khi hợp đồng chuyển giao ghi rõ; đưa đóng tài nguyên vào một phạm vi `try-with-resources` duy nhất.
6. **Áp dụng cú pháp Java 9 khi có lợi.** `private` interface helper, `try (existingEffectivelyFinalResource)`, anonymous diamond. Đừng dùng chỉ để thay đổi hình thức nếu làm người đọc khó hiểu hơn.
7. **Chạy test/compile trên target.** Với bài này: `javac --release 9 -Xlint:all`, chạy hai chương trình và đối chiếu stdout. Trong sản phẩm, dùng compiler/target CI tương ứng môi trường hỗ trợ.
8. **Đánh giá tác động public API.** Không tự xóa/ẩn method đã được client dùng; nếu thay hợp đồng, có migration guide và chiến lược versioning.
9. **Đọc lại code từ góc nhìn người dùng.** Code call-site có suy luận `T` đúng không? Có mở file mà không đóng? Có đoạn helper bị lộ ra API không? Lỗi parse có bị biến thành “thành công một phần” không?

## 12. Bài tập mở rộng

**Bài A — Thêm kiểu dữ liệu khác.** Tạo `Customer` với `static Customer fromLine(String)`, sau đó dùng **chính `RowParser<T>` và `load(...)`**. Nếu phải copy/paste vòng lặp đọc file sang class mới, thiết kế chưa đạt mục tiêu tái sử dụng.

**Bài B — Tách chính sách distinct.** Đổi yêu cầu nghiệp vụ: duplicate được xác định chỉ theo mã hàng. Thiết kế lại bằng cách truyền một hàm trích xuất key `Function<? super T, ? extends K>` hoặc strategy phù hợp; kiểm tra thứ tự xuất hiện. Đừng lạm dụng việc đổi `Item.equals` nếu equality toàn hệ thống còn có nghĩa khác.

**Bài C — Mở rộng resource.** Giả sử đọc một input và đồng thời ghi lỗi parse ra output. Dùng hai resource trong cùng `try-with-resources`, xác minh thứ tự đóng và suppressed exception khi writer close lỗi.

**Bài D — Đọc dữ liệu rất lớn.** `readAll` đang tích lũy toàn bộ `List<T>` trong RAM. Với hàng triệu dòng, thiết kế một callback/consumer hoặc streaming API để xử lý từng phần, nhưng phải đặc biệt chú ý **vòng đời reader còn mở trong lúc stream được tiêu thụ**. Không trả `Stream<T>` tham chiếu reader đã đóng.

**Bài E — Kiểm tra biến không effectively final.** Cố tình gán lại reader trước `try (reader)`, quan sát lỗi compile; sửa bằng cách tạo một resource mới và một `try` riêng. Không giải quyết bằng cách vô hiệu cảnh báo.

## 13. Câu hỏi tự đánh giá

1. Vì sao `private` trong interface là công cụ refactor thực tế từ Java 9, thay vì chỉ thêm một `default` method khác?
2. `RowParser<T>` có hai default methods và một private method thì có còn là functional interface không?
3. Khi chuyển `List<Item>` sang `List<Object>`, vì sao gán trực tiếp bị từ chối nhưng `copyInto` vẫn hợp lệ?
4. Trong `copyInto`, nguồn và đích tương ứng với vế nào của PECS?
5. `try (reader)` khác gì so với `try (BufferedReader reader = ...)` và điều kiện biên dịch nào quan trọng?
6. Nếu `parse(line)` ném `NumberFormatException`, có cần viết thêm `reader.close()` ở `catch` không?
7. Với `try (first; second)`, tài nguyên nào được đóng trước và lỗi close được lưu ở đâu nếu body đã lỗi?
8. Vì sao `LinkedHashSet<Item>` lọc đúng `A,2` nhưng không nhất thiết lọc `A,3`?
9. Khi muốn hỗ trợ file CSV có ô chứa dấu phẩy và dấu ngoặc kép, nên sửa gì?
10. Tại sao cần kiểm thử hành vi và hợp đồng public API bên cạnh việc chạy `javac`?

**Đáp án ngắn:** (1) Giữ helper nội bộ và tránh mở rộng API public; (2) có, chỉ một abstract method là `parse`; (3) invariant nhưng wildcard cho phép đọc nguồn subtype và ghi vào consumer supertype; (4) nguồn extends, đích super; (5) Java 9 cho dùng biến hiện có final/effectively final; (6) không, `try-with-resources` đóng reader; (7) `second` rồi `first`, lỗi close suppressed nếu đã có primary; (8) equality gồm code và count; (9) dùng CSV parser theo chuẩn giao thức; (10) refactor còn ảnh hưởng logic, compatibility và ownership.

## 14. Tài liệu chính thức (API còn được hỗ trợ)

- [Oracle Java SE 25 — Java Language Changes by Release](https://docs.oracle.com/en/java/javase/25/language/java-language-changes-release.html): các thay đổi Java 9, gồm private interface methods, anonymous-class diamond và try-with-resources với biến effectively final.
- [Java Language Specification SE 25 — Interface Method Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.4): quy tắc method trong interface, private/default/static.
- [Java Language Specification SE 25 — The try Statement](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.20): resource specification, thứ tự đóng, exception và suppression.
- [Java Language Specification SE 25 — Type Arguments and Generics](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.5): parameterized types và nguyên tắc kiểm tra kiểu.
- [Oracle Java SE 25 API — AutoCloseable](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/AutoCloseable.html).
- [Oracle Java SE 25 API — Files](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html).
- [Oracle Java SE 25 API — LinkedHashSet](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/LinkedHashSet.html).

**Kết luận:** Tái cấu trúc thành công không chỉ là “ít dòng code hơn”. Thiết kế tốt phân biệt **contract công khai của interface**, **kiểu dữ liệu và chiều đọc/ghi theo generic**, và **ai sở hữu tài nguyên**. Private interface helper, wildcard PECS và `try-with-resources` Java 9 giúp ba ranh giới này rõ ràng hơn, đồng thời duy trì mã dễ kiểm tra trên các JDK hiện hành.