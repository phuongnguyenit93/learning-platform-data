# StringJoiner.merge và kết hợp kết quả trong Java 8

## 1. Vì sao cần merge thay vì tự nối chuỗi?

Khi xây dựng một chuỗi có **delimiter** (dấu phân cách), **prefix** (tiền tố) và **suffix** (hậu tố), `java.util.StringJoiner` giúp loại bỏ việc phải tự kiểm tra “đây có phải phần tử đầu tiên không?”. Chẳng hạn `new StringJoiner(", ", "[", "]")` tạo ra danh sách dạng `[A, B, C]`.

Nhưng một chương trình thực tế không phải lúc nào cũng gom dữ liệu ở cùng một chỗ. Có thể một phương thức xử lý nhóm A, phương thức khác xử lý nhóm B, hoặc một luồng `Stream` chia dữ liệu thành các phần rồi kết hợp kết quả. Khi đó ta có **nhiều StringJoiner đã chứa dữ liệu**, cần gộp chúng mà vẫn chỉ có **một cặp prefix/suffix ở bên ngoài**.

Phương thức `StringJoiner.merge(StringJoiner other)` giải quyết nhu cầu đó. Theo hợp đồng Java 8:

> Khi nguồn `other` không rỗng, `merge` thêm **phần nội dung của nguồn, không có prefix/suffix nguồn**, làm **một phần tử kế tiếp** của StringJoiner đích. Nếu nguồn rỗng, lời gọi không thay đổi đích.

Điều này tạo ra khác biệt quan trọng với `String.concat`, `String.join` hay việc gọi `add(other.toString())`:

```text
Đích:   StringJoiner(", ", "[", "]")   -> [Java, 8]
Nguồn:  StringJoiner(" | ", "{", "}")  -> {Stream | Lambda}

Đích.merge(Nguồn)                   -> [Java, 8, Stream | Lambda]
Đích.add(Nguồn.toString())          -> [Java, 8, {Stream | Lambda}]
```

Cách thứ nhất **loại wrapper nguồn** và đưa nội dung của nó vào đích. Cách thứ hai **giữ nguyên chuỗi đã format của nguồn như một phần tử**. Cả hai đều có thể có ích, nhưng chúng **không tương đương**.

Bài Knowledge này tập trung vào đúng đề tài **“StringJoiner.merge và kết hợp kết quả”** thuộc nhóm **Chuỗi và Base64**, module **Java 8**. Bài trình bày hợp đồng API, trạng thái rỗng, dấu phân cách khác nhau, tính thay đổi được của đối tượng, nguồn và đích, ghép các kết quả theo nhóm, combiner trong Stream Collector, các lỗi thường gặp khi xử lý song song, các giới hạn về escape/CSV/JSON, kiểm thử và bài tập. Tất cả mã dùng API Java 8 vẫn được hỗ trợ hiện nay. Sáu chương trình Java độc lập đã được biên dịch với `javac --release 8` và chạy để đối chiếu stdout.

**Mục tiêu cuối:** biết chính xác khi nào `merge` gộp được kết quả mong muốn, khi nào phải giữ nguyên cấu trúc nhóm bằng `add(other.toString())`, vì sao delimiter của nguồn không bị thay thế, và cách dùng `StringJoiner::merge` đúng trong bộ gom dữ liệu có thể chạy song song.

## 2. Nhắc lại StringJoiner: delimiter, prefix và suffix

`StringJoiner` có hai constructor Java 8:

```java
StringJoiner plain = new StringJoiner(", ");
StringJoiner wrapped = new StringJoiner(", ", "[", "]");
```

Constructor thứ nhất không thêm prefix/suffix; constructor thứ hai sử dụng ba thành phần:

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| `delimiter` | Chuỗi được đặt **giữa các phần tử** được thêm | `", "` |
| `prefix` | Chuỗi đứng **đầu** biểu diễn của joiner | `"["` |
| `suffix` | Chuỗi đứng **cuối** biểu diễn của joiner | `"]"` |
| `add(CharSequence)` | Thêm một phần tử (có thể là chuỗi rỗng) | `add("A")` |
| `toString()` | Tạo biểu diễn hiện tại | `"[A, B]"` |
| `length()` | Độ dài biểu diễn hiện tại | Bằng `toString().length()` |
| `setEmptyValue(CharSequence)` | Biểu diễn khi chưa thêm phần tử | `"EMPTY"` |
| `merge(StringJoiner)` | Thêm nội dung nguồn (không wrapper) vào đích | Phương thức trọng tâm |

Ví dụ ngắn:

```java
// Snippet dùng khi đã import java.util.StringJoiner.
StringJoiner parts = new StringJoiner(" / ", "<", ">");
parts.add("A").add("B");
System.out.println(parts); // <A / B>
```

Hai quy tắc cần giữ:

1. `delimiter` nằm **giữa các lần add/merge có nội dung thực**, không phải ở trước phần tử đầu hay sau phần tử cuối.
2. `prefix` và `suffix` thuộc **biểu diễn của joiner**, không được coi là nội dung phần tử để khi gộp joiner có thể tự động có nhiều lớp wrapper.

Phần tử được thêm không được parse hoặc escape theo một định dạng đặc biệt: nếu phần tử chứa chính dấu phân cách, StringJoiner **giữ nguyên ký tự đó**. Đây là công cụ định dạng/ghép chuỗi, không phải parser hay bộ mã hóa dữ liệu.

## 3. Chữ ký và hợp đồng của merge

Chữ ký Java 8:

```java
public StringJoiner merge(StringJoiner other)
```

Ba điều quan trọng:

- Phương thức **thay đổi đối tượng đích `this`**, không tạo một StringJoiner đích mới.
- Nó **trả về chính `this`**, cho phép chaining: `a.merge(b).merge(c)`.
- Tham số `other` phải khác `null`; truyền null ném `NullPointerException`.

Về nội dung:

- Nếu `other` đã có phần tử, phần bên trong prefix/suffix của nó được đưa vào đích thành **một đơn vị nội dung**.
- Nếu `other` rỗng theo định nghĩa của StringJoiner, đích không thay đổi.
- Prefix và suffix của nguồn **không được lồng** vào prefix/suffix của đích.
- Delimiter của **đích** dùng để ngăn cách nội dung đã có với khối được merge.
- Delimiter **bên trong nguồn** tiếp tục xuất hiện giữa các phần tử nguồn; không tự bị thay bằng delimiter của đích.
- Source StringJoiner vẫn được dùng tiếp; `merge` không phải thao tác rút hết hoặc tiêu thụ nguồn.
- Nếu đã merge xong rồi chỉnh sửa nguồn, biểu diễn đã ghép của đích không tự động cập nhật theo nguồn.

### Mô hình chuỗi kết quả

Giả sử `target` đã chứa `T1,T2` và `other` chứa `U1|U2`:

```text
target:
  delimiter=","    prefix="[" suffix="]"
  content=T1,T2

other:
  delimiter="|"    prefix="{" suffix="}"
  content=U1|U2

target.merge(other)

target:
  prefix + T1 + "," + T2 + "," + "U1|U2" + suffix
  = [T1,T2,U1|U2]
```

Chú ý `"U1|U2"` được thêm vào đích như **một khối**, không phải hai lần `target.add("U1"); target.add("U2");`. Từ biểu diễn `[T1,T2,U1|U2]`, người đọc không thể tự kết luận có bốn phần tử cùng cấp nếu delimiter khác nhau.

## 4. Chương trình 1 — merge bỏ wrapper nguồn, giữ nội dung và trả lại đích

Tệp **`MergeBasicsDemo.java`** dùng prefix/suffix khác nhau cho hai StringJoiner. Mã kiểm tra chuỗi đích, trạng thái nguồn, object identity của kết quả trả về và tính nhất quán của length.

```java
import java.util.StringJoiner;

public class MergeBasicsDemo {
    static void check(boolean ok, String reason) {
        if (!ok) throw new AssertionError(reason);
    }

    public static void main(String[] args) {
        StringJoiner destination =
            new StringJoiner(", ", "[", "]");
        destination.add("Java").add("8");

        StringJoiner source =
            new StringJoiner(" | ", "{", "}");
        source.add("Stream").add("Lambda");

        StringJoiner returned = destination.merge(source);

        check(destination == returned,
              "merge returns destination");
        check("[Java, 8, Stream | Lambda]"
              .equals(destination.toString()), "merged output");
        check("{Stream | Lambda}"
              .equals(source.toString()), "source unchanged");

        System.out.println("merged=" + destination);
        System.out.println("source=" + source);
        System.out.println("sameDestination="
            + (returned == destination));
        System.out.println("lengthMatches="
            + (destination.length()
               == destination.toString().length()));
        System.out.println("PASS");
    }
}
```

Biên dịch và chạy với JDK 8:

```bash
javac -encoding UTF-8 MergeBasicsDemo.java
java MergeBasicsDemo
```

Nếu dùng JDK mới và muốn chắc chắn chỉ phụ thuộc Java 8:

```bash
javac --release 8 -encoding UTF-8 MergeBasicsDemo.java
java MergeBasicsDemo
```

**Stdout đã kiểm chứng:**

```text
merged=[Java, 8, Stream | Lambda]
source={Stream | Lambda}
sameDestination=true
lengthMatches=true
PASS
```

**Giải thích kết quả:**

1. Đích giữ dấu ngoặc vuông `[ ]` của chính nó.
2. Ngoặc nhọn `{ }` của nguồn bị loại khỏi phần được merge.
3. Dấu `" | "` bên trong nguồn giữ nguyên, nên thành `"Stream | Lambda"`.
4. Đích dùng `", "` để ngăn khối nguồn với phần tử đích trước đó.
5. Nguồn vẫn có biểu diễn `{Stream | Lambda}`, không bị clear.
6. `returned == destination` xác nhận merge trả chính đích, giúp chaining.
7. `length()` khớp độ dài của biểu diễn `toString()`.

**Lưu ý:** không phải cứ source có hai phần tử thì target sẽ có đúng hai lời gọi add độc lập. Khi khác delimiter, hai phần tử nguồn được gắn dưới dạng một khối văn bản chứa dấu phân cách nguồn.

## 5. Rỗng nghĩa là chưa có phần tử, không phải “chuỗi biểu diễn dài bằng 0”

Đây là phần rất dễ nhầm khi gộp các kết quả.

Một StringJoiner được coi là **empty** nếu **chưa gọi `add()`** và chưa từng `merge()` với một StringJoiner nguồn **không rỗng**.

Biểu diễn của joiner rỗng:

- Mặc định: `prefix + suffix` (có thể là chuỗi rỗng nếu không có wrapper).
- Nếu gọi `setEmptyValue("...")`: dùng chuỗi custom này trước khi có phần tử.

Ví dụ:

```java
StringJoiner a = new StringJoiner(",", "(", ")");
System.out.println(a); // ()

a.setEmptyValue("EMPTY");
System.out.println(a); // EMPTY
```

Nếu nguồn có `setEmptyValue("NO_SOURCE")` nhưng **chưa thêm phần tử**, merge nguồn đó không đưa chữ `NO_SOURCE` vào đích. Empty value là **biểu diễn trong trường hợp empty**, không phải dữ liệu phần tử.

### Tại sao merge với nguồn rỗng không có tác dụng?

Mục tiêu là hỗ trợ ghép các nhóm dữ liệu, trong đó một nhóm có thể không có bản ghi. Nếu mọi nhóm rỗng tự thêm chuỗi `"[]"` hoặc `"EMPTY"` vào kết quả, chuỗi tổng sẽ chứa nhiều đoạn biểu diễn rỗng không mong muốn.

```text
target = "A"
other  = empty StringJoiner với toString() = "NO_SOURCE"

target.merge(other) -> "A"
                        (không thêm "NO_SOURCE")
```

### Nhưng `add("")` khiến StringJoiner không còn rỗng

Đây là điều khác hẳn với “chưa add”.

```java
StringJoiner sj = new StringJoiner(",", "(", ")");
sj.setEmptyValue("EMPTY");
sj.add("");
System.out.println(sj); // ()
```

Sau `add("")`, joiner **đã nhận một phần tử** dù độ dài nội dung phần tử bằng 0. Biểu diễn chuyển từ `EMPTY` về `()`. Nếu thêm tiếp `"X"`, kết quả là `(,X)`, bởi dấu phân cách xuất hiện giữa phần tử rỗng và phần tử X.

**Quy tắc nghiệp vụ:** “không có phần tử” khác “có một phần tử có nội dung chuỗi rỗng”. Khi dữ liệu có giá trị rỗng thật, phải quyết định rõ có bỏ qua nó hay giữ lại, trước khi gọi `add` hoặc `merge`.

## 6. Chương trình 2 — nguồn rỗng, emptyValue và phần tử chuỗi rỗng

Tệp **`MergeEmptyDemo.java`** chủ động phân biệt hai trạng thái “empty joiner” và “joiner đã add một chuỗi rỗng”.

```java
import java.util.StringJoiner;

public class MergeEmptyDemo {
    static void check(boolean ok, String reason) {
        if (!ok) throw new AssertionError(reason);
    }

    public static void main(String[] args) {
        StringJoiner destination =
            new StringJoiner(",", "(", ")");
        destination.setEmptyValue("EMPTY");

        StringJoiner source =
            new StringJoiner(";", "{", "}");
        source.setEmptyValue("NO_SOURCE");

        String before = destination.toString();
        destination.merge(source);
        String afterEmptyMerge = destination.toString();

        source.add("");
        destination.merge(source);
        String afterEmptyText = destination.toString();
        destination.add("X");

        check("EMPTY".equals(before),
              "custom empty destination");
        check("EMPTY".equals(afterEmptyMerge),
              "empty source has no effect");
        check("()".equals(afterEmptyText),
              "empty string element changes state");
        check("(,X)".equals(destination.toString()),
              "delimiter after empty element");

        System.out.println("before=" + before);
        System.out.println("sourceEmptyValue=" + "NO_SOURCE");
        System.out.println("afterEmptySource=" + afterEmptyMerge);
        System.out.println("afterEmptyStringElement=" + afterEmptyText);
        System.out.println("afterAddX=" + destination);
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 MergeEmptyDemo.java
java MergeEmptyDemo
```

**Stdout đã kiểm chứng:**

```text
before=EMPTY
sourceEmptyValue=NO_SOURCE
afterEmptySource=EMPTY
afterEmptyStringElement=()
afterAddX=(,X)
PASS
```

**Đọc lần lượt:**

- Ban đầu đích chưa thêm gì nên `toString()` trả emptyValue riêng là `EMPTY`.
- Nguồn cũng chưa có phần tử nên dù biểu diễn của nó là `NO_SOURCE`, `merge` vẫn **không thay đổi đích**.
- Gọi `source.add("")` làm nguồn không còn empty theo API. Merge lúc này thêm một **phần tử có nội dung rỗng** vào đích, khiến đích chuyển sang biểu diễn mặc định `()`.
- Sau khi `destination.add("X")`, có delimiter `","` giữa phần tử rỗng và X: `(,X)`.

Một bài kiểm thử chỉ nhìn thấy `toString()` của nguồn sau `add("")` có thể không đủ để biết nguồn **có phần tử nhưng rỗng về chữ**. Hãy kiểm semantics qua cách nguồn được xây dựng, không suy ngược số phần tử từ biểu diễn chuỗi.

## 7. Delimiter của nguồn khác delimiter của đích

Khi hai joiner cùng delimiter, kết quả merge **trông như** một danh sách các phần tử cùng cấp:

```text
target(","; [ ]) = [A,B]
other (","; { }) = {C,D}
target.merge(other) = [A,B,C,D]
```

Nhưng với delimiter khác nhau, merge không “tách lại” nội dung nguồn:

```text
target("/") = north
other (";") = east;west

target.merge(other) = north/east;west
```

Dấu `";"` của nguồn vẫn nằm trong phần nội dung đã merge. Lý do là JavaDoc định nghĩa “nội dung nguồn được thêm như **một phần tử kế tiếp** của đích” khi delimiter khác nhau.

Điều này cực quan trọng khi kết hợp:

- Nhiều nhóm có format separator khác nhau.
- Kết quả từ nhiều thành phần/service.
- Các định dạng có cấu trúc phân cấp, ví dụ đường dẫn hoặc danh sách lồng.
- Dữ liệu đã chứa delimiter trong chính text.

### Merge không phải parser

`StringJoiner.merge` **không đọc nguồn theo từng phần tử semantic rồi add từng phần tử vào đích**. Nó không có API truy xuất danh sách phần tử nguồn hoặc bảo đảm phân biệt dấu separator là ký tự dữ liệu hay separator thật.

Nếu bạn cần “mọi phần tử của mọi nguồn phải có cùng delimiter mới”, hãy giữ **dữ liệu thô** dưới dạng `List<String>`, collection hoặc stream và nối lại bằng một delimiter thống nhất. Không cố split chuỗi đã format của StringJoiner một cách mù quáng, vì phần tử có thể chứa delimiter.

## 8. Chương trình 3 — khác delimiter và tính độc lập của nguồn sau merge

Tệp **`MergeDelimitersDemo.java`** dùng `"/"` cho đích, `";"` cho nguồn, rồi thay đổi nguồn sau merge. Chương trình kiểm tra rằng kết quả đã merge của đích không tự động cập nhật theo nguồn.

```java
import java.util.StringJoiner;

public class MergeDelimitersDemo {
    static void check(boolean ok, String reason) {
        if (!ok) throw new AssertionError(reason);
    }

    public static void main(String[] args) {
        StringJoiner destination =
            new StringJoiner("/", "(", ")");
        destination.add("north");

        StringJoiner source =
            new StringJoiner(";", "<", ">");
        source.add("east").add("west");

        destination.merge(source).add("south");
        String mergedBeforeSourceChanges =
            destination.toString();

        source.add("later");
        String sourceAfter = source.toString();

        StringJoiner elementWise =
            new StringJoiner("/", "(", ")");
        elementWise.add("north").add("east")
                   .add("west").add("south");

        check("(north/east;west/south)"
              .equals(mergedBeforeSourceChanges),
              "source delimiter preserved");
        check("(north/east;west/south)"
              .equals(destination.toString()),
              "source mutation cannot change old merge");
        check("<east;west;later>".equals(sourceAfter),
              "source is still reusable");
        check(!destination.toString()
              .equals(elementWise.toString()),
              "merge does not tokenize source");

        System.out.println("merged=" + destination);
        System.out.println("sourceAfter=" + source);
        System.out.println("elementWise=" + elementWise);
        System.out.println("mergeReparsedElements=false");
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 MergeDelimitersDemo.java
java MergeDelimitersDemo
```

**Stdout đã kiểm chứng:**

```text
merged=(north/east;west/south)
sourceAfter=<east;west;later>
elementWise=(north/east/west/south)
mergeReparsedElements=false
PASS
```

Kết quả chỉ rõ:

1. Đích vẫn có `"("` và `")"`.
2. Cặp `"<"` và `">"` của nguồn không bị đưa vào đích.
3. Delimiter `";"` giữa east và west **không bị thay thành "/"**.
4. Các phần tử đích thêm sau merge tiếp tục dùng `"/"`, nên có `"/south"`.
5. `source.add("later")` không sửa lại nội dung đã merge trong đích.
6. Nếu thật sự muốn bốn phần tử cùng cấp ngăn cách bởi `"/"`, kết quả phải là `elementWise`, được xây từ dữ liệu riêng từng phần tử.

**Lỗi thường gặp:** nghĩ `merge` sẽ áp lại delimiter của đích cho từng phần tử nguồn. Không có bước re-tokenize đó.

## 9. Merge theo nhóm: có muốn giữ cấu trúc lồng hay không?

Một trường hợp quan trọng trong thiết kế output là **sự khác nhau giữa gộp phẳng và lồng nhóm**.

Giả sử bạn muốn hiển thị một danh sách gồm phần tử A và nhóm B,C.

**Cách A — merge nội dung, bỏ wrapper nhóm:**

```java
StringJoiner inner = new StringJoiner(",", "[", "]");
inner.add("B").add("C");

StringJoiner outer = new StringJoiner(",", "(", ")");
outer.add("A").merge(inner);

// outer.toString() là "(A,B,C)"
```

**Cách B — add biểu diễn đầy đủ của nhóm như một phần tử:**

```java
StringJoiner inner = new StringJoiner(",", "[", "]");
inner.add("B").add("C");

StringJoiner outer = new StringJoiner(",", "(", ")");
outer.add("A").add(inner.toString());

// outer.toString() là "(A,[B,C])"
```

Khi cần **bỏ wrapper** để tạo một chuỗi liền, chọn merge. Khi cần **hiển thị wrapper của nhóm**, chọn add(inner.toString()) hoặc giữ cấu trúc dữ liệu và dùng serializer phù hợp.

### Không có “merge lồng nhóm” tự động

`StringJoiner` chỉ xây biểu diễn văn bản. Nó không duy trì một cây phần tử để bạn hỏi “có bao nhiêu nhóm con?”, “nhóm nào chứa các phần tử này?”, hay “dấu ngoặc nào là metadata của nhóm”. Nếu cấu trúc nhóm quan trọng về nghiệp vụ, nên giữ model (List/List, Map, DTO) cho đến bước xuất dữ liệu cuối.

### Base64 có thay thế việc escape delimiters không?

Không trực tiếp. Base64 là **cách mã hóa byte thành ký tự**, không phải quy tắc parse một StringJoiner. Một payload Base64 chuẩn có thể chứa các ký tự `+`, `/` và `=`; nếu bạn chọn `"/"` làm delimiter rồi nối các payload Base64, ký tự `"/"` có thể đồng thời thuộc payload và delimiter. Khi cần một giao thức dữ liệu đáng tin cậy, dùng framing rõ ràng, độ dài, escape/encoding được xác định hoặc định dạng serialization phù hợp thay vì dựa vào merge để phân cách dữ liệu tùy ý.

## 10. Chương trình 4 — merge làm phẳng, add giữ nested và thứ tự nhóm ảnh hưởng kết quả

Tệp **`MergeGroupsDemo.java`** so sánh hai cách xây output và minh họa việc kết hợp các nguồn có **delimiter khác nhau** theo những cấu trúc nhóm khác nhau.

```java
import java.util.StringJoiner;

public class MergeGroupsDemo {
    static void check(boolean ok, String reason) {
        if (!ok) throw new AssertionError(reason);
    }

    public static void main(String[] args) {
        StringJoiner source =
            new StringJoiner(",", "[", "]");
        source.add("B").add("C");

        StringJoiner flattened =
            new StringJoiner(",", "(", ")");
        flattened.add("A").merge(source);

        StringJoiner nested =
            new StringJoiner(",", "(", ")");
        nested.add("A").add(source.toString());

        StringJoiner leftAssoc =
            new StringJoiner(",", "(", ")");
        leftAssoc.add("A")
            .merge(new StringJoiner("|").add("B").add("C"))
            .merge(new StringJoiner("~").add("D").add("E"));

        StringJoiner rightAssocSource =
            new StringJoiner("|");
        rightAssocSource.add("B").add("C")
            .merge(new StringJoiner("~").add("D").add("E"));

        StringJoiner rightAssoc =
            new StringJoiner(",", "(", ")");
        rightAssoc.add("A").merge(rightAssocSource);

        check("(A,B,C)".equals(flattened.toString()),
              "merge drops source wrapper");
        check("(A,[B,C])".equals(nested.toString()),
              "add retains nested wrapper");
        check("(A,B|C,D~E)".equals(leftAssoc.toString()),
              "left grouping");
        check("(A,B|C|D~E)".equals(rightAssoc.toString()),
              "right grouping");
        check(!leftAssoc.toString()
              .equals(rightAssoc.toString()),
              "different delimiters: grouping matters");

        System.out.println("flattened=" + flattened);
        System.out.println("nested=" + nested);
        System.out.println("leftGrouped=" + leftAssoc);
        System.out.println("rightGrouped=" + rightAssoc);
        System.out.println("groupingsEqual="
            + leftAssoc.toString()
                       .equals(rightAssoc.toString()));
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 MergeGroupsDemo.java
java MergeGroupsDemo
```

**Stdout đã kiểm chứng:**

```text
flattened=(A,B,C)
nested=(A,[B,C])
leftGrouped=(A,B|C,D~E)
rightGrouped=(A,B|C|D~E)
groupingsEqual=false
PASS
```

**Bài học ngữ nghĩa:**

- `merge` loại wrapper của nhóm nguồn, tạo `(A,B,C)`.
- `add(source.toString())` bảo toàn wrapper của nhóm, tạo `(A,[B,C])`.
- Với các delimiter `","`, `"|"` và `"~"` khác nhau, **cấu trúc merge** ảnh hưởng chuỗi output vì các nội dung nguồn được thêm thành từng khối.
- Do đó, đừng coi phép merge của các StringJoiner có cấu hình delimiter bất kỳ là phép toán giao hoán/kết hợp trên **các phần tử nguyên bản** theo một nghĩa tùy tiện.
- Khi dùng merge làm combiner của collector, các accumulator cần có **cùng quy tắc định dạng**, và thứ tự kết hợp phải tuân contract của stream/collector để tạo output dự kiến.

## 11. Dùng merge làm combiner trong Stream Collector

Một ứng dụng rất quan trọng của `StringJoiner.merge` là **gộp kết quả tích lũy từ nhiều phần của luồng**.

Java 8 `Stream.collect` có thể sử dụng một collector gồm:

1. **supplier**: tạo accumulator mới.
2. **accumulator**: nhận từng phần tử và cập nhật accumulator của phần việc đó.
3. **combiner**: ghép hai accumulators khi luồng được xử lý theo nhiều phần.
4. **finisher**: biến accumulator thành kết quả cuối cùng.

Với StringJoiner:

```java
Collector<String, StringJoiner, String> collector =
    Collector.of(
        () -> new StringJoiner(", ", "[", "]"),
        StringJoiner::add,
        StringJoiner::merge,
        StringJoiner::toString
    );
```

Các method references tương ứng:

| Vai trò | Biểu thức | Ý nghĩa |
| --- | --- | --- |
| Supplier | `() -> new StringJoiner(", ", "[", "]")` | Mỗi accumulator mới dùng chung cấu hình |
| Accumulator | `StringJoiner::add` | Thêm một phần tử vào accumulator |
| Combiner | `StringJoiner::merge` | Gộp nội dung accumulator phải vào trái |
| Finisher | `StringJoiner::toString` | Tạo String kết quả |

### Tại sao merge phù hợp cho combiner?

- Các accumulator được tạo với **cùng delimiter, prefix và suffix**, nên khi merge một phần bên phải, chỉ nội dung cần được thêm; wrapper không bị lặp.
- Accumulator nguồn rỗng là trường hợp thường gặp khi một nhánh không có phần tử; merge bỏ qua nó, giúp giữ đúng empty behavior.
- Chaining/mutation của combiner phù hợp với API yêu cầu combiner trả accumulator đã kết hợp.
- Với stream có **encounter order** và collector không tuyên bố UNORDERED, kết quả ghép cần tương thích với thứ tự các phần tử theo hợp đồng Stream. Không suy rằng scheduler thực thi từng task theo thứ tự 1→N; hệ thống thu kết quả theo cơ chế collector.

### Điều không nên làm

Không viết:

```java
// Anti-pattern: nhiều thread có thể gọi add trên cùng joiner.
StringJoiner shared = new StringJoiner(",");
items.parallelStream().forEach(shared::add);
```

`StringJoiner` **không có bảo đảm thread-safe** cho việc nhiều thread đồng thời gọi `add`/`merge` trên cùng một instance. Cách trên có thể sinh race, mất phần tử, sai thứ tự hoặc trạng thái không xác định.

Dùng `collect` với supplier/accumulator/combiner như trên: mỗi phần tích lũy có thể được xử lý riêng, rồi combiner ghép theo hợp đồng. **Không đánh dấu collector là CONCURRENT** khi accumulator của nó không an toàn cho nhiều thread cùng ghi.

## 12. Chương trình 5 — Stream tuần tự, song song và Collectors.joining

Tệp **`MergeCollectorDemo.java`** tạo collector tùy biến với `StringJoiner::merge`, chạy trên stream tuần tự và stream song song có encounter order, rồi so với `Collectors.joining` sẵn có.

```java
import java.util.*;
import java.util.stream.*;

public class MergeCollectorDemo {
    static void check(boolean ok, String reason) {
        if (!ok) throw new AssertionError(reason);
    }

    static String collectWithMerge(boolean parallel) {
        Collector<String, StringJoiner, String> collector =
            Collector.of(
                () -> new StringJoiner(", ", "[", "]"),
                StringJoiner::add,
                StringJoiner::merge,
                StringJoiner::toString
            );

        Stream<String> stream =
            IntStream.rangeClosed(1, 8)
                     .mapToObj(Integer::toString);
        if (parallel) stream = stream.parallel();

        return stream.collect(collector);
    }

    public static void main(String[] args) {
        String sequential = collectWithMerge(false);
        String parallel = collectWithMerge(true);

        String builtIn =
            IntStream.rangeClosed(1, 8)
                .mapToObj(Integer::toString)
                .parallel()
                .collect(Collectors.joining(", ", "[", "]"));

        for (int i = 0; i < 20; i++) {
            check(collectWithMerge(true).equals(sequential),
                  "ordered parallel stream");
        }

        String empty =
            Stream.<String>empty().collect(Collector.of(
                () -> new StringJoiner(", ", "[", "]"),
                StringJoiner::add,
                StringJoiner::merge,
                StringJoiner::toString
            ));

        check("[1, 2, 3, 4, 5, 6, 7, 8]"
              .equals(sequential), "expected");
        check(sequential.equals(parallel)
              && parallel.equals(builtIn), "parallel matches");
        check("[]".equals(empty), "empty result");

        System.out.println("sequential=" + sequential);
        System.out.println("parallel=" + parallel);
        System.out.println("builtIn=" + builtIn);
        System.out.println("empty=" + empty);
        System.out.println("twentyParallelRunsMatched=true");
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 MergeCollectorDemo.java
java MergeCollectorDemo
```

**Stdout đã kiểm chứng:**

```text
sequential=[1, 2, 3, 4, 5, 6, 7, 8]
parallel=[1, 2, 3, 4, 5, 6, 7, 8]
builtIn=[1, 2, 3, 4, 5, 6, 7, 8]
empty=[]
twentyParallelRunsMatched=true
PASS
```

**Vì sao parallel ở đây vẫn giữ thứ tự 1..8?**

- `IntStream.rangeClosed(1,8)` có encounter order.
- Collector được tạo bằng `Collector.of` thông thường không được đánh dấu UNORDERED hay CONCURRENT.
- Các accumulator dùng cùng cấu hình, kết quả từ mỗi phân đoạn được merge theo contract của pipeline có thứ tự.
- Việc gọi 20 lần kiểm tính nhất quán của ví dụ, **không phải phép chứng minh mọi collector do người dùng tự viết đều đúng**.

Nếu nguồn là một stream không có encounter order hoặc chính bạn gọi `unordered()`, không nên yêu cầu kết quả giữ thứ tự giống ví dụ. Khi cần thứ tự theo một trường nghiệp vụ, hãy sắp xếp dữ liệu trước hoặc thu kết quả theo index phù hợp.

### Khi nào không cần tự viết collector?

Nếu chỉ muốn tạo String với delimiter/prefix/suffix từ một stream, dùng:

```java
// Đoạn minh họa.
String text = stream.collect(
    Collectors.joining(", ", "[", "]"));
```

`Collectors.joining` có sẵn trong Java 8, diễn đạt ý định đơn giản hơn và tránh lỗi tự viết accumulator/combiner/finisher.

Tự viết collector có ý nghĩa khi cần thêm logic vào quá trình tích lũy, muốn kiểm soát kết quả trung gian hoặc phục vụ một thuật toán ghép có contract riêng. Nhưng ngay cả khi custom, nên dùng `StringJoiner::merge` chỉ khi cấu hình joiner và cách chia/ghép phù hợp.

## 13. Asssociativity, identity và tính đúng của collector

Một collector dùng trong stream song song cần tính đúng với việc dữ liệu được chia ra và gộp lại theo nhiều cách. Hai quy tắc nền tảng:

**Identity:** gộp một accumulator **rỗng** được tạo bởi supplier vào một accumulator đã chứa dữ liệu không được làm thay đổi kết quả hiển thị.

**Associativity:** với dữ liệu và cùng cấu hình joiner, các cách chia tập đầu vào thành các phần rồi ghép lại hợp lệ phải tạo ra kết quả tương đương cách tích lũy tuần tự theo encounter order.

`StringJoiner.merge` hỗ trợ các quy tắc này trong cách dùng như `Collectors.joining`, với supplier nhất quán và các dữ liệu phần tử được tích lũy bởi `add`.

### Vì sao delimiter khác nhau làm vấn đề phức tạp?

Ví dụ chương trình `MergeGroupsDemo` đã cho:

```text
Gộp theo nhóm trái:  (A,B|C,D~E)
Gộp theo nhóm phải: (A,B|C|D~E)
```

Khi b và c có delimiter khác nhau, cách nhóm merge thay đổi chỗ xuất hiện của delimiter, nên hai kết quả không bằng nhau.

**Bởi vậy, đừng lấy nhiều accumulator được tạo với delimiter thay đổi theo dữ liệu rồi mặc định áp `StringJoiner::merge` làm combiner parallel.** Nếu output phải có một delimiter chuẩn, hãy chuẩn hóa tại nơi **tạo accumulator và thêm từng phần tử**, không chờ đến merge để “sửa” delimiter nguồn.

### Kết hợp thứ tự và luật nghiệp vụ

Ngay cả cùng delimiter, nối A rồi B sẽ tạo chuỗi khác nối B rồi A:

```text
[A] + [B] -> [A,B]
[B] + [A] -> [B,A]
```

Tính chất này không phải lỗi của StringJoiner; chuỗi là một cấu trúc **có thứ tự**. Nếu bạn muốn thứ tự đầu ra độc lập scheduling, cần giữ encounter order hoặc sort. Nếu chỉ cần một tập không có thứ tự, đừng dùng thứ tự chữ trong output như một invariant bắt buộc khi dữ liệu đầu vào vốn unordered.

## 14. Merge thay đổi đích nhưng không “ăn mất” nguồn

Hai biến:

```java
StringJoiner left = new StringJoiner(",");
StringJoiner right = new StringJoiner("|");

left.add("A");
right.add("B").add("C");

left.merge(right);
```

Sau đó:

- `left.toString()` là `A,B|C`.
- `right.toString()` vẫn là `B|C`.
- Nếu sau đó `right.add("D")`, left **không tự biến thành** `A,B|C|D`.
- Nếu sau đó `left.add("E")`, left thành `A,B|C,E`, dùng delimiter `","` của chính left.

Điều này phù hợp khi một nhóm trung gian cần được tái sử dụng ở nhiều output. Tuy nhiên StringJoiner là **mutable object**: nếu nhiều thread cùng giữ reference và sửa nó, bạn vẫn phải có cách đồng bộ riêng. Việc `merge` không thay đổi nguồn trong use case được kiểm thử **không** có nghĩa có thể gọi các mutation đồng thời lên nguồn/đích bất kỳ và vẫn an toàn.

### Có cần clone StringJoiner không?

`StringJoiner` không cung cấp API copy constructor/clone công khai cho mục đích deep copy logical elements. Nếu bạn cần nhiều biến thể output cùng một danh sách phần tử, hãy giữ **list dữ liệu gốc** rồi tạo mỗi StringJoiner từ list. Nếu chỉ cần kết quả text hiện tại, gọi `toString()` để lấy một String bất biến.

### Đừng dùng toString để “khôi phục” phần tử gốc

Khi output đã chứa dấu phân cách giống nội dung phần tử, không thể split nó để khôi phục chính xác mọi phần tử nếu chưa có quy tắc escape. Ví dụ một phần tử `"a,b"` được add vào joiner delimiter `","` sẽ tạo chuỗi có dấu phẩy, nhưng dấu phẩy đó **thuộc dữ liệu**, không phải separator. Merge không làm mất delimiter trong dữ liệu nhưng cũng không giúp bạn phân biệt chúng.

## 15. add(null), merge(null), chuỗi rỗng và CharSequence mutable

Hai phương thức có hành vi **khác nhau** với null.

### add(null)

Theo JavaDoc Java 8, `add(null)` **thêm chuỗi chữ `"null"`**. Nó không bỏ qua phần tử và không ném NullPointerException.

```java
StringJoiner j = new StringJoiner(",");
j.add(null);
System.out.println(j); // null
```

Nếu dữ liệu thực sự là `null` và chính sách nghiệp vụ muốn **bỏ qua**, bạn phải kiểm tra trước khi add:

```java
// Snippet minh họa.
if (value != null) {
    joiner.add(value);
}
```

Nếu muốn một biểu diễn khác, hãy map giá trị theo domain trước. Không để chữ `null` xuất hiện tình cờ trong báo cáo người dùng nếu nó không có ý nghĩa.

### merge(null)

`merge(null)` ném `NullPointerException`; nó không được định nghĩa như “bỏ qua joiner null”.

```java
// Snippet minh họa.
if (source != null) {
    destination.merge(source);
}
```

Tùy hợp đồng, source null có thể là lỗi cần báo thay vì bỏ qua. Đừng nuốt NullPointerException vô điều kiện.

### add("") không giống joiner rỗng

`add("")` thêm một phần tử có nội dung 0 ký tự. Delimiter vẫn xuất hiện trước/sau nó khi có phần tử kế bên. Đó là lý do ví dụ `MergeNullAndCharSequenceDemo` có hai dấu `"|"` liên tiếp.

### CharSequence được sao chép khi add

`StringJoiner.add(CharSequence)` thêm một **bản sao nội dung ký tự**. Nếu truyền `StringBuilder` mutable rồi sửa builder, giá trị đã add không tự đổi.

Đây là khác biệt với việc lưu trực tiếp một reference mutable trong List. Nhưng StringJoiner vẫn mutable đối với các lời gọi add/merge tiếp theo trên chính nó.

## 16. Chương trình 6 — null, chuỗi rỗng và snapshot của CharSequence

Tệp **`MergeNullAndCharSequenceDemo.java`** kiểm `add(null)`, `add("")`, một phần tử chứa delimiter, nội dung StringBuilder được sao chép và `merge(null)` bị từ chối.

```java
import java.util.StringJoiner;

public class MergeNullAndCharSequenceDemo {
    static void check(boolean ok, String reason) {
        if (!ok) throw new AssertionError(reason);
    }

    public static void main(String[] args) {
        StringJoiner joiner =
            new StringJoiner("|", "[", "]");
        joiner.add(null).add("").add("a,b");

        StringBuilder mutable =
            new StringBuilder("first");
        StringJoiner copied = new StringJoiner(",");
        copied.add(mutable);
        mutable.append("-changed");

        boolean nullMergeRejected = false;
        try {
            joiner.merge(null);
        } catch (NullPointerException ex) {
            nullMergeRejected = true;
        }

        check("[null||a,b]".equals(joiner.toString()),
              "null and empty element rendered");
        check("first".equals(copied.toString()),
              "CharSequence copied at add");
        check(nullMergeRejected,
              "merge null fails");

        System.out.println("joined=" + joiner);
        System.out.println("copied=" + copied);
        System.out.println("builderAfter=" + mutable);
        System.out.println("nullMergeRejected="
            + nullMergeRejected);
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 MergeNullAndCharSequenceDemo.java
java MergeNullAndCharSequenceDemo
```

**Stdout đã kiểm chứng:**

```text
joined=[null||a,b]
copied=first
builderAfter=first-changed
nullMergeRejected=true
PASS
```

**Giải thích:**

1. `add(null)` thêm chữ `null`.
2. `add("")` thêm phần tử chuỗi rỗng nên kết quả có hai separator `"|"` liên tiếp.
3. Phần tử `"a,b"` chứa dấu phẩy, nhưng delimiter của joiner là `"|"`, do đó nội dung được giữ nguyên.
4. Chuỗi `first` được sao chép khi add StringBuilder; sửa builder thành `first-changed` không sửa giá trị đã add.
5. `merge(null)` ném NullPointerException, được test ghi nhận.

Đây là hành vi của API Java 8, không phải quy tắc domain để chấp nhận mọi giá trị null. Trong hệ thống thật, việc bỏ qua hoặc định dạng null phải do nghiệp vụ quyết định.

## 17. Dùng merge để kết hợp kết quả nhiều hàm

Một pattern dễ áp dụng là mỗi hàm nhỏ trả một StringJoiner cho phần dữ liệu mình xử lý:

```java
// Snippet minh họa, không phải chương trình standalone.
static StringJoiner joinNames(List<String> names) {
    StringJoiner result = new StringJoiner(", ", "[", "]");
    for (String name : names) {
        result.add(name);
    }
    return result;
}
```

Gộp:

```java
StringJoiner output = new StringJoiner(", ", "[", "]");
output.merge(joinNames(groupA));
output.merge(joinNames(groupB));
String text = output.toString();
```

Lợi thế:

- Mỗi hàm xử lý nhóm và có thể được unit test độc lập.
- Merge không lặp wrapper `[ ]` của từng nhóm.
- Nhóm rỗng bị bỏ qua tự nhiên.
- Chỉ stringify một lần ở bước cuối, thay vì ghép kết quả đã có wrapper rồi phải trim thủ công.

**Điều kiện:** các nhóm nên dùng **cùng delimiter và cùng ý nghĩa phần tử**, nếu output cần một danh sách phẳng đồng nhất. Nếu một nhóm có dấu phân cách khác hoặc chứa dữ liệu có thể tạo mơ hồ, nên gộp **dữ liệu thô** trước khi format.

### Nếu các nhóm được xử lý theo thứ tự khác nhau?

Tự thực thi hàm cho các nhóm A, B, C và gọi merge theo thứ tự C, A, B sẽ tạo output theo C, A, B, không tự sắp xếp lại. Khi nhóm đại diện cho khoảng dữ liệu cần đúng thứ tự, hãy giữ index nhóm và thực hiện merge theo index, hoặc sử dụng stream có encounter order và collector đúng. Fork/Join hay CompletableFuture không tự đưa output StringJoiner về thứ tự dữ liệu gốc nếu bạn chỉ merge ngay khi task hoàn thành.

## 18. Khi nào nên dùng Collectors.joining thay vì StringJoiner trực tiếp?

Có ba mức thao tác với chuỗi thường gặp:

| Bài toán | API thường hợp lý |
| --- | --- |
| Ghép một vài String literal thành một chuỗi | `String.join(delimiter, parts...)` |
| Xây chuỗi dần, có prefix/suffix và thêm phần tử theo nhánh if/loop | `StringJoiner` |
| Chuyển Stream thành chuỗi có delimiter/prefix/suffix | `Collectors.joining(delimiter,prefix,suffix)` |
| Gộp nhiều accumulator StringJoiner độc lập | `StringJoiner.merge` |
| Format văn bản có quy tắc phức tạp, escape, indentation | `StringBuilder` hoặc formatter/serializer phù hợp |
| Tạo CSV/JSON/XML đúng quy chuẩn | Thư viện serializer/encoder đúng định dạng |

Ví dụ tiện lợi:

```java
List<String> names = Arrays.asList("Ada", "Lin", "Ken");

String a = String.join(" / ", names);
// Ada / Lin / Ken

String b = names.stream()
    .collect(Collectors.joining(" / ", "<", ">"));
// <Ada / Lin / Ken>
```

Những snippet trên giả định import `java.util.*` và `java.util.stream.Collectors`, chưa phải class độc lập. Cả hai API đều có trong Java 8.

**Khi chỉ muốn xuất output của Stream**, dùng Collectors.joining sẽ gọn và rõ hơn custom collector với merge. Khi đang có nhiều đối tượng StringJoiner thực sự chứa kết quả trung gian, merge là lựa chọn trực tiếp và tránh lặp prefix/suffix.

## 19. Không hiểu nhầm merge với concatenate, flatten, tokenization và escaping

Bốn hành vi khác nhau:

1. **Concatenation thô:** `a.toString() + b.toString()` nối hai biểu diễn hoàn chỉnh, thường lặp prefix/suffix.
2. **Merge nội dung:** `a.merge(b)` chỉ đưa nội dung không wrapper của b vào a.
3. **Tokenize rồi join lại:** lấy từng phần tử nguyên bản, add vào một joiner đích với delimiter mới. StringJoiner không cung cấp API iterating original elements.
4. **Escape/serialize:** bảo đảm dữ liệu chứa separator/ký tự đặc biệt vẫn có thể được parse ngược theo định dạng; cần encoder phù hợp.

### CSV

Ví dụ:

```java
new StringJoiner(",")
    .add("Alice")
    .add("New York, USA")
    .toString();
```

sẽ tạo một chuỗi có dấu phẩy trong dữ liệu mà không tự thêm dấu ngoặc kép theo quy tắc CSV. Một CSV parser có thể đọc thành **ba cột** thay vì hai nếu bạn dùng output này làm CSV trực tiếp. Dùng CSV library với quy tắc quote/escape đúng.

### JSON

`new StringJoiner(",", "[", "]").add("hello")` tạo `[hello]`, không phải JSON array string hợp lệ vì thiếu dấu quote quanh string. Merge không tự tạo JSON syntax. Dùng JSON serializer; không cố ghép JSON bằng StringJoiner khi dữ liệu tùy ý.

### URL và Base64

StringJoiner không URL-encode, không Base64-encode và không escape. Khi nối các payload Base64, URL segments hoặc query parameters, cần chọn định dạng phân tách có thể parse ngược và áp encoding tương ứng. Dấu `"/"` trong Base64 chuẩn là một ví dụ khiến delimiter `"/"` không còn đơn nghĩa.

### Hierarchical text

Nếu muốn hiển thị `[root,[leaf1,leaf2]]`, dùng add(inner.toString()) để giữ dấu ngoặc của inner, nhưng với nội dung chứa dấu ngoặc/dấu phẩy, output vẫn chỉ là text. Với dữ liệu cấu trúc thật, hãy dùng object tree và serializer thay vì phụ thuộc cách biểu diễn.

## 20. Tính biến đổi được và an toàn luồng

`StringJoiner` là một **mutable builder**. Các phương thức `add` và `merge` làm biến đổi joiner nhận lời gọi. Nó **không được định nghĩa là concurrent accumulator thread-safe**.

Các pattern nên dùng:

- Một StringJoiner chỉ thuộc một phương thức/luồng hoặc giai đoạn xử lý cụ thể.
- Nếu cần gộp các kết quả từ nhiều thread, mỗi thread xây joiner **riêng**, sau đó dùng một giai đoạn phối hợp có quyền sở hữu rõ ràng để merge.
- Trong Stream song song, để **Collector** quản lý accumulator tách biệt và gọi combiner phù hợp.
- Khi kết quả đã ổn định và muốn chia sẻ, công bố `String` từ `toString()` thay vì tiếp tục chia sẻ builder mutable.

**Không làm:**

```java
// Anti-pattern, không phải ví dụ runnable an toàn.
StringJoiner shared = new StringJoiner(",");
parallelStream.forEach(shared::add);
```

Đoạn trên có thể làm nhiều worker gọi add đồng thời trên cùng object. Không có bảo đảm correctness và thứ tự output.

### Có cần synchronized quanh StringJoiner không?

Nếu thật sự phải chia sẻ một joiner mutable, có thể đồng bộ mọi thao tác sửa và đọc theo một lock thống nhất, nhưng việc giữ thứ tự output vẫn là bài toán riêng. Nhiều trường hợp **không chia sẻ joiner** và dùng collect/reduction sẽ đơn giản hơn. Đừng tự giả định đồng bộ chỉ khi merge là đủ nếu nơi khác vẫn gọi add/toString không theo cùng protocol.

### Thread-safe khác deterministic ordering

Ngay cả nếu một shared accumulator được bảo vệ bằng lock, kết quả có thể theo **thứ tự đến của thread** chứ không phải thứ tự dữ liệu ban đầu. Muốn kết quả ổn định, giữ index/encounter order hoặc sắp xếp trước giai đoạn xuất chuỗi. Tính thread-safe của mutation không tự tạo tính deterministic cho nghiệp vụ.

## 21. Trạng thái source sau merge và việc tái sử dụng kết quả

Một số câu hỏi thường gặp:

**Nếu merge từ A vào B, A có bị xóa không?**  
Không theo hành vi quan sát của API trong trường hợp hợp lệ; A vẫn có thể `toString()`/`add()` sau merge, và B giữ nội dung đã gộp tại thời điểm merge.

**Có nên reuse một StringJoiner trong nhiều kết quả khác nhau không?**  
Có thể nếu kiểm soát biến đổi và thứ tự sử dụng. Tuy nhiên nếu các kết quả phải độc lập và được xử lý cạnh tranh, nên tạo accumulator riêng để tránh shared mutable state.

**Có thể giữ StringJoiner để merge lại cùng source nhiều lần không?**  
Có thể gọi merge nhiều lần, nhưng **nội dung sẽ được thêm lặp** nếu source không rỗng. API không ghi nhận “nguồn này đã merge một lần rồi”. Trong quy trình tổng hợp cần tránh duplicate, dùng ID/đánh dấu dữ liệu ở tầng nghiệp vụ.

**Nếu source rỗng và setEmptyValue khác rỗng, merge có thêm emptyValue không?**  
Không. Đây là biểu diễn rỗng, không phải phần tử.

**Nếu source chỉ có add("") thì sao?**  
Source đã không rỗng; merge tạo ra một phần tử nội dung rỗng ở đích, có thể làm thay đổi trạng thái biểu diễn của đích.

**Nếu source có prefix/suffix giống đích thì sao?**  
Merge vẫn bỏ wrapper của source, nên kết quả thường không có wrapper lồng. Điều này đúng khi muốn một danh sách phẳng.

**Nếu source có delimiter khác đích thì sao?**  
Delimiter trong source giữ nguyên bên trong khối được merge, không được chuẩn hóa thành delimiter đích.

## 22. length() đếm gì?

`StringJoiner.length()` trả độ dài của **chuỗi biểu diễn hiện tại**, tương đương `toString().length()`.

Điều này có nghĩa:

- Bao gồm prefix/suffix khi joiner đã có phần tử.
- Bao gồm delimiters và nội dung đã add/merge.
- Khi joiner empty, có thể là độ dài `prefix+suffix` hoặc `emptyValue` tùy cấu hình.
- Dùng cách đếm `String.length()` của Java: **số UTF-16 code units**, không nhất thiết là số grapheme clusters hoặc số ký tự người đọc thấy.

Vì vậy `length()` không phải “số phần tử đã add” hoặc “số kết quả đã merge”. `StringJoiner` không có phương thức public `size()` trả số phần tử. Nếu cần đếm số phần tử để báo cáo/kiểm tra, hãy tự đếm ở dữ liệu đầu vào hoặc duy trì counter đúng ngữ nghĩa.

**Ví dụ Unicode:** một emoji ngoài BMP có thể chiếm hai UTF-16 code units trong Java. Đừng dùng length() để khẳng định số ký tự hiển thị hoặc chiều rộng trên UI. Nếu cần giới hạn byte của network payload, hãy dùng số byte sau khi mã hóa Charset thích hợp, không dùng StringJoiner.length.

## 23. Kiểm thử merge như một đơn vị nghiệp vụ

Một bộ test tốt cần bao phủ:

| Ca kiểm thử | Input | Kết quả quan trọng |
| --- | --- | --- |
| Merge thông thường | Đích và nguồn đều có nội dung | Wrapper của đích, nội dung nguồn không wrapper |
| Source prefix/suffix khác | `[A]` + `{B}` | Không tự lồng `{ }` |
| Source delimiter khác | Đích `"/"`, nguồn `";"` | Delimiter nguồn giữ nguyên |
| Source trống | Chưa gọi add vào nguồn | Đích không đổi |
| Source có setEmptyValue | Nguồn emptyValue="N/A" | Không merge chữ N/A |
| Source đã `add("")` | Một phần tử chuỗi rỗng | Đích thay đổi trạng thái empty |
| Target empty, source nonempty | `merge` vào joiner chưa có phần tử | Có nội dung nguồn, dùng wrapper đích |
| Null source | `merge(null)` | NullPointerException |
| Null phần tử | `add(null)` | Thêm chữ "null" |
| CharSequence mutable | add StringBuilder rồi sửa builder | Nội dung đã add giữ bản sao |
| Source dùng lại | `source.add(...)` sau merge | Destination không tự đổi |
| Merge lặp cùng source | `merge(source)` hai lần | Có nội dung nguồn hai lần |
| Destination object identity | `returned == target` | true |
| Chaining | `a.merge(b).add("X")` | Trả đích, có thể chain |
| `add(inner.toString())` vs merge | Có wrapper nguồn | Hai kết quả khác nhau |
| Khác grouping khi delimiter khác nhau | Merge b/c theo hai cây | Kết quả có thể khác |
| Collector tuần tự | Stream có thứ tự | Output khớp mong đợi |
| Collector song song | Stream ordered, non-CONCURRENT collector | Output khớp mô hình tuần tự |
| Stream empty | Không có phần tử | Có prefix+suffix hoặc empty value theo contract |
| Chia stream thành partitions | Gộp các accumulators cùng cấu hình | Wrapper không lặp |
| Concurrent shared joiner | Nhiều thread gọi add cùng object | Không được giả định thread-safe |
| Dữ liệu chứa delimiter | `"a,b"` với separator "," | Không tự escape |
| Định dạng CSV/JSON | Dữ liệu có quote/separator | Không phải serializer |
| Length | `length` và `toString().length` | Bằng nhau, không phải element count |

Một lưu ý khi chạy test song song: kết quả đúng sau 20 lần chạy không chứng minh một thuật toán custom thread-safe trong mọi tình huống, nhưng giúp kiểm tính ổn định cho ví dụ. Với ứng dụng thật, cần kiểm quy tắc collector, đặc biệt associativity/identity, encounter order và các side effects.

## 24. Các lỗi thiết kế thường gặp

| Lỗi | Nguyên nhân | Hướng sửa |
| --- | --- | --- |
| Gộp bằng `target.add(source.toString())` rồi mong wrapper nguồn mất | add thêm toàn bộ biểu diễn như một phần tử | Dùng merge nếu muốn bỏ wrapper |
| Dùng merge nhưng muốn giữ nested group | merge bỏ prefix/suffix nguồn | add(source.toString()) hoặc serializer |
| Nghĩ source delimiter sẽ thành target delimiter | merge giữ text bên trong source | Gộp từ danh sách phần tử gốc |
| Nghĩ merge là phép split + add từng phần tử | Source không cung cấp API element list | Giữ data model trước định dạng |
| Merge một source rỗng và mong emptyValue xuất hiện | Empty source bị bỏ qua | Add emptyValue có chủ đích nếu business muốn |
| Nghĩ `add("")` vẫn empty | Một add đã làm joiner nonempty | Phân biệt empty element và no element |
| Truyền `merge(null)` | Hợp đồng không cho null | Validate source |
| Truyền `add(null)` và mong bị bỏ qua | API thêm chữ "null" | Filter/map null theo domain |
| Gọi `parallelStream().forEach(shared::add)` | StringJoiner không thread-safe | Dùng Collector hoặc per-task joiner |
| Khai báo collector CONCURRENT với StringJoiner | Nhiều thread có thể dùng chung accumulator không an toàn | Không đặt CONCURRENT |
| Trộn delimiter khác nhau trong collector | Grouping thay đổi output | Supplier nhất quán, normalized input |
| Mong parallel callbacks chạy theo thứ tự dữ liệu | Scheduler không bảo đảm thứ tự xử lý | Giữ encounter order/sort |
| Dùng merge để tạo CSV/JSON | Không tự escape/quote | Dùng serializer đúng chuẩn |
| Dùng StringJoiner.length() để đếm phần tử | Length là độ dài text | Đếm từ input |
| Dùng length() làm byte-size | Java String.length đếm UTF-16 | Encode rồi đếm byte |
| Tạo nhiều lần `toString()` trong vòng lặp lớn | Tạo chuỗi trung gian không cần thiết | Tích lũy rồi stringify một lần |
| Nghĩ merge xóa nguồn | Source vẫn dùng được | Quản lý lifecycle rõ |
| Nghĩ nguồn sửa sau merge sẽ sửa đích | Merge không giữ liên kết live với nguồn | Merge lại khi cần output mới |
| Gộp lặp cùng source nhưng không muốn duplicate | Merge không deduplicate | Dedup tại tầng dữ liệu |
| Lấy output đã format rồi split để parse ngược | Delimiter có thể nằm trong dữ liệu | Giữ structured data/escape scheme |
| Dùng StringJoiner như thư viện Base64 | Joiner chỉ ghép text | Dùng Base64.Encoder/Decoder khi cần mã hóa |

## 25. Bài tập thực hành có đáp án

### Bài 1 — wrapper của ai?

**Đề:** A = `new StringJoiner(",", "[", "]").add("x")`, B = `new StringJoiner("|", "{", "}").add("y").add("z")`. Sau `A.merge(B)`, `A.toString()` là gì?

**Đáp án:** `[x,y|z]`. Đích giữ `[ ]`, bỏ `{ }`, giữ delimiter `|` nằm trong nội dung nguồn.

### Bài 2 — đích hay nguồn bị thay đổi?

**Đề:** `StringJoiner x = a.merge(b)`. `x == a` đúng hay sai?

**Đáp án:** đúng. `merge` trả `this`, tức a; a được cập nhật. b không bị rút hết nội dung.

### Bài 3 — nguồn rỗng tùy biến

**Đề:** B mới được tạo, gọi `B.setEmptyValue("EMPTY")` nhưng không add. `A.merge(B)` có thêm chữ EMPTY vào A không?

**Đáp án:** không. B vẫn empty theo định nghĩa API, merge không có tác dụng.

### Bài 4 — phần tử chuỗi rỗng

**Đề:** B đã gọi `add("")`; B còn được xem là empty không?

**Đáp án:** không. Dù biểu diễn nội dung phần tử rỗng, B đã được thêm một phần tử, nên merge có thể làm A thay đổi.

### Bài 5 — hai delimiter

**Đề:** A dùng `"/"`, có `"east"`. B dùng `";"`, có `"north"` và `"south"`. A.merge(B) có thay dấu ; bằng / không?

**Đáp án:** không. Kết quả biểu diễn là `east/north;south`.

### Bài 6 — định dạng nhóm lồng

**Đề:** muốn `(root,[child1,child2])`, nên `outer.merge(inner)` hay `outer.add(inner.toString())`?

**Đáp án:** `outer.add(inner.toString())` nếu muốn giữ `[ ]` của inner. Merge sẽ bỏ wrapper nguồn.

### Bài 7 — combiner của Collector

**Đề:** một Collector tạo StringJoiner mới qua supplier, thêm mỗi phần tử bằng add. Combiner nên dùng gì?

**Đáp án:** thường là `StringJoiner::merge` nếu mọi accumulator dùng cùng cấu hình và đáp ứng quy tắc identity/associativity của collector.

### Bài 8 — thread safety

**Đề:** dùng một StringJoiner chung rồi gọi `parallelStream().forEach(joiner::add)`. Có an toàn mặc định không?

**Đáp án:** không. StringJoiner không phải concurrent accumulator. Dùng `collect(Collectors.joining(...))` hoặc custom collector có accumulator độc lập và combiner đúng.

### Bài 9 — thứ tự khi song song

**Đề:** fork nhiều task, mỗi task hoàn tất rồi merge ngay vào một joiner đích. Có chắc output theo thứ tự index task không?

**Đáp án:** không nếu chỉ theo completion order. Cần giữ index/encounter order, sắp xếp hoặc dùng collector với contract thứ tự phù hợp.

### Bài 10 — null

**Đề:** `add(null)` và `merge(null)` có cùng kết quả không?

**Đáp án:** không. `add(null)` thêm chữ `null`; `merge(null)` ném NullPointerException.

### Bài 11 — source sau merge

**Đề:** A.merge(B), sau đó B.add("new"). A có tự thêm "new" không?

**Đáp án:** không. A đã nhận nội dung B tại thời điểm merge, không giữ liên kết live tới builder B.

### Bài 12 — CSV

**Đề:** dữ liệu gồm hai field `"Alice"` và `"New York, USA"`. Dùng StringJoiner(",") có đủ để xuất CSV hai cột đúng chuẩn không?

**Đáp án:** không. Field thứ hai chứa dấu phẩy, cần quote/escape CSV. StringJoiner không phải CSV serializer.

### Bài 13 — Base64

**Đề:** hai Base64 payload chuẩn có thể chứa dấu `/`. Nối bằng delimiter `/` có dễ tách ngược không?

**Đáp án:** không chắc, vì delimiter có thể xuất hiện trong payload. Dùng framing hoặc encoding/serialization có quy tắc tách rõ.

### Bài 14 — độ dài

**Đề:** joiner có hai phần tử nhưng prefix/suffix dài. `length()` có trả 2 không?

**Đáp án:** không. Nó trả số UTF-16 code units trong `toString()`, bao gồm wrapper, delimiter và nội dung.

### Bài 15 — giống delimiter nhưng nguồn có nhiều phần tử

**Đề:** A dùng dấu phẩy, B cũng dùng dấu phẩy. A.merge(B) trông như nhiều phần tử được add riêng. Điều đó có nghĩa merge đã trả một danh sách phần tử B để duyệt không?

**Đáp án:** không. Đây chỉ là cách biểu diễn text; API không cung cấp iterable gốc sau merge. Để xử lý logic trên từng phần tử, phải giữ collection gốc.

### Bài 16 — thay đổi grouping

**Đề:** hai cách `a.merge(b).merge(c)` và `a.merge(b.merge(c))` có chắc bằng nhau với mọi delimiter tùy ý không?

**Đáp án:** không. Khi các nguồn dùng delimiter khác, cách lồng khối được merge có thể làm output khác nhau. Ví dụ đã kiểm chứng trong `MergeGroupsDemo`.

## 26. Câu hỏi tự đánh giá

**1.** `StringJoiner.merge` thêm gì từ nguồn? — Nội dung không có prefix/suffix, như một phần tử tiếp theo nếu nguồn nonempty.

**2.** `merge` có thay đổi source không? — Không trong cách sử dụng API đã minh họa; source vẫn dùng được.

**3.** `merge` trả gì? — Chính StringJoiner đích, để chaining.

**4.** Source empty và có `setEmptyValue("N/A")` có đưa N/A vào target không? — Không.

**5.** Source đã `add("")` còn empty không? — Không.

**6.** Delimiter của source khác target có bị viết lại không? — Không; nó vẫn nằm trong nội dung khối source.

**7.** Khi muốn giữ ngoặc nhóm source, dùng gì? — `add(source.toString())` thay vì merge.

**8.** Khi muốn bỏ ngoặc source, dùng gì? — `merge(source)`.

**9.** Có dùng merge để parse JSON/CSV không? — Không.

**10.** `StringJoiner` có thread-safe cho nhiều thread cùng add không? — Không có bảo đảm đó.

**11.** Trong Collector, combiner có thể dùng gì? — `StringJoiner::merge` với supplier nhất quán và contract đúng.

**12.** Cách gọn nhất để join Stream với prefix/suffix? — `Collectors.joining(delimiter,prefix,suffix)`.

**13.** `add(null)` làm gì? — Thêm chuỗi chữ `null`.

**14.** `merge(null)` làm gì? — Ném NullPointerException.

**15.** `length()` đo gì? — Số UTF-16 code units của biểu diễn `toString()`.

**16.** Merge một source hai lần có tự loại trùng không? — Không.

**17.** Merge đã format có tự biến delimiter dữ liệu thành delimiter target không? — Không.

**18.** StringJoiner dùng để tạo Base64 không? — Không; Base64 encoding là API khác.

**19.** Parallel stream có bắt buộc theo thứ tự kết thúc worker không? — Không; encounter order và collector contract mới quan trọng.

**20.** Nếu business cần xử lý từng phần tử sau merge nên giữ gì? — Collection/structured model gốc, không chỉ chuỗi đã nối.

## Tài liệu chính thức

- [Java SE 8 — StringJoiner](https://docs.oracle.com/javase/8/docs/api/java/util/StringJoiner.html): constructor, add, merge, setEmptyValue, length, toString và định nghĩa trạng thái empty.
- [Java SE 26 — StringJoiner](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/StringJoiner.html): xác nhận StringJoiner và merge vẫn là API hiện hành.
- [Java SE 8 — Collectors](https://docs.oracle.com/javase/8/docs/api/java/util/stream/Collectors.html): `joining` có delimiter/prefix/suffix.
- [Java SE 8 — Collector](https://docs.oracle.com/javase/8/docs/api/java/util/stream/Collector.html): supplier, accumulator, combiner, finisher, identity và associativity.
- [Java SE 8 — Stream](https://docs.oracle.com/javase/8/docs/api/java/util/stream/Stream.html): collect, parallel, encounter order.
- [Java SE 8 — String](https://docs.oracle.com/javase/8/docs/api/java/lang/String.html): `String.join` và `String.length`.
- [Java SE 8 — CharSequence](https://docs.oracle.com/javase/8/docs/api/java/lang/CharSequence.html): hợp đồng giao diện dữ liệu chuỗi.
- [Java SE 8 — Base64](https://docs.oracle.com/javase/8/docs/api/java/util/Base64.html): API mã hóa/giải mã bytes bằng Base64, độc lập với StringJoiner.

**Ghi nhớ:** `StringJoiner.merge(other)` **sửa joiner đích**, giữ prefix/suffix và delimiter của đích, loại prefix/suffix của nguồn, đồng thời thêm phần nội dung nguồn theo một khối nếu nguồn nonempty. Nó **không phân tích lại từng phần tử**, không thay delimiter bên trong nguồn, không dùng emptyValue của một nguồn trống và không tự làm output có cấu trúc thành CSV/JSON hợp lệ. Trong Stream, `StringJoiner::merge` là combiner hữu ích khi các accumulator có cấu hình nhất quán và collector tuân quy tắc thứ tự/identity/associativity; để join Stream đơn giản, ưu tiên `Collectors.joining`. Giữ StringJoiner private trong giai đoạn tích lũy, không chia sẻ mutable joiner cho các luồng song song mà thiếu đồng bộ.