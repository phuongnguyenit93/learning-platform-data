# Chuẩn hóa tập giá trị bằng Set.copyOf trong Java

## 1. Bài toán thực hành: từ dữ liệu không đồng nhất đến tập giá trị chuẩn

Giả sử một hệ thống nhận danh sách nhãn từ giao diện nhập liệu, file cấu hình, API hoặc nhiều nguồn khác nhau:

~~~text
" Java "
"JAVA"
" api "
"API"
" Streams "
"streams"
~~~

Với chính sách nghiệp vụ coi nhãn không phân biệt chữ hoa/thường và bỏ khoảng trắng hai đầu, sáu chuỗi đầu vào chỉ tương ứng **ba giá trị có ý nghĩa**:

~~~text
api
java
streams
~~~

Mục tiêu của bài thực hành tổng hợp là xây dựng một quy trình:

1. **Kiểm tra đầu vào**: từ chối một collection null, phần tử null hoặc nhãn chỉ có khoảng trắng nếu chính sách không cho phép.
2. **Chuẩn hóa giá trị**: đưa cùng một ý nghĩa về một dạng biểu diễn thống nhất, ví dụ bỏ khoảng trắng rìa, chuyển chữ thường và chuẩn hóa Unicode NFC khi phù hợp.
3. **Loại phần tử trùng theo equality**: những nhãn có cùng dạng chuẩn chỉ xuất hiện một lần.
4. **Đóng băng cấu trúc tập kết quả**: không cho caller thêm hoặc xóa phần tử.
5. **Trả kết quả không phụ thuộc thứ tự duyệt**: khi cần output/log/JSON ổn định thì sắp xếp riêng.
6. **Kiểm chứng ngữ nghĩa**: nguồn đổi sau khi tạo không làm tập kết quả đổi; null và thao tác sửa tập bị từ chối theo hợp đồng.

API chủ đạo:

~~~java
Set<String> result = Set.copyOf(normalizedValues);
~~~

`Set.copyOf(Collection<? extends E>)` được giới thiệu trong **Java 10**, vẫn được hỗ trợ trong **Java 17/21/25** và các JDK hiện đại. Đây là giải pháp tạo **tập không chỉnh sửa được (unmodifiable Set)** từ một `Collection` đã có.

**Điểm quan trọng nhất:** `Set.copyOf` **không tự trim, không tự lower-case và không tự chuẩn hóa Unicode**. Nó chỉ tạo tập theo quy tắc bình đẳng phần tử `equals` của dữ liệu đã được đưa vào. Nếu yêu cầu nghiệp vụ nói "Java", "JAVA" và " Java " là cùng một nhãn, người viết code phải **chuẩn hóa trước**, rồi mới gọi `Set.copyOf`.

## 2. Hợp đồng chính thức của Set.copyOf

### 2.1. Khai báo phương thức

Theo Oracle Java SE 17/25 Javadoc của `java.util.Set`:

~~~java
static <E> Set<E> copyOf(Collection<? extends E> coll)
~~~

Giải thích:

- `E` là kiểu phần tử của tập kết quả.
- `Collection<? extends E>` cho phép truyền `List<E>`, `Set<E>` hoặc collection có phần tử thuộc một subtype thích hợp.
- Kết quả là một `Set<E>` **không chỉnh sửa được qua các mutator methods**.
- `coll` và mọi phần tử của `coll` **không được null**.
- Nếu collection có các phần tử trùng nhau theo `equals`, tập kết quả chỉ giữ **một phần tử đại diện** cho mỗi nhóm trùng; không ném lỗi chỉ vì trùng.
- Nếu collection nguồn được sửa sau đó, **tập kết quả không phản ánh thay đổi cấu trúc của nguồn**.
- Thứ tự duyệt phần tử trong tập là **không được bảo đảm**.
- Nếu nguồn đã là một unmodifiable set, implementation có thể **tái sử dụng instance** thay vì cấp phát một instance mới.

Ví dụ nhỏ:

~~~java
var source = new java.util.ArrayList<>(
        java.util.List.of("red", "blue", "red"));
var snapshot = java.util.Set.copyOf(source);

System.out.println(snapshot.size());          // 2
System.out.println(snapshot.contains("red")); // true
~~~

Không in trực tiếp `snapshot` rồi kiểm bằng một chuỗi như `[red, blue]`, bởi iteration order không nằm trong contract.

### 2.2. Một số bất biến nên kiểm

Với mọi `Set<String> result` được tạo đúng từ collection hợp lệ:

~~~text
result != null
result.size() >= 0
result không chứa hai phần tử bằng nhau theo equals
result không chứa null
result không cho phép add/remove/clear
nguồn đổi cấu trúc sau đó không đổi thành viên trong result
~~~

Nhưng **không có** bất biến:

~~~text
result.iterator() có cùng thứ tự với source
result luôn là một object instance mới
result có elements bất biến sâu
result tự chuẩn hóa chữ hoa/thường hoặc Unicode
result giữ phần tử đầu tiên trong nhóm các phần tử trùng
~~~

Những khẳng định này sẽ dẫn tới lỗi trong code và tests nếu không được sửa lại.

### 2.3. Null: từ chối trực tiếp, không âm thầm bỏ qua

~~~java
var values = java.util.Arrays.asList("a", null, "b");
var result = java.util.Set.copyOf(values);
~~~

Lệnh `Set.copyOf(values)` ném `NullPointerException` vì collection chứa null.

Tương tự:

~~~java
java.util.Collection<String> values = null;
java.util.Set.copyOf(values); // NullPointerException
~~~

Không viết `List.of("a", null)` để minh họa lỗi riêng của `Set.copyOf`: bản thân `List.of` đã từ chối null trước khi gọi `Set.copyOf`. Muốn kiểm chính API `copyOf` với collection chứa null, dùng collection cho phép null như `Arrays.asList` hoặc `ArrayList`.

Nếu chính sách ứng dụng muốn **bỏ qua null**, phải làm rõ và thực hiện bước lọc có chủ đích trước `copyOf`. Không ngầm hiểu API sẽ tự lọc.

### 2.4. Trùng lặp: loại bớt, không ném IllegalArgumentException

~~~java
Set<String> values = Set.copyOf(
        List.of("a", "a", "b"));
System.out.println(values.size()); // 2
~~~

Với `Set.copyOf`, trùng lặp trong đầu vào là **hợp lệ** và được gộp.

Đối chiếu:

~~~java
Set.of("a", "a"); // IllegalArgumentException
~~~

`Set.of` (Java 9) được thiết kế cho danh sách các phần tử bạn truyền trực tiếp và **từ chối phần tử trùng** khi khởi tạo; `Set.copyOf` (Java 10) nhận một `Collection` và **gộp phần tử trùng**. Đừng đồng nhất hai hợp đồng chỉ vì kết quả đều là unmodifiable set.

### 2.5. Nếu hai object bằng nhau nhưng không cùng identity

Theo hợp đồng `Set.copyOf`, khi collection có nhiều object `a.equals(b) == true` nhưng `a != b`, **một object đại diện bất kỳ** trong nhóm có thể được giữ lại.

Ví dụ:

~~~java
record Tag(String key, String display) {
    @Override
    public boolean equals(Object other) {
        return other instanceof Tag tag
                && key.equals(tag.key);
    }

    @Override
    public int hashCode() {
        return key.hashCode();
    }
}
~~~

Hai instance `new Tag("java", "Java")` và `new Tag("java", "JAVA")` có thể bằng nhau theo `key`, nhưng `display` khác. Nếu dùng `Set.copyOf` trên cả hai rồi lấy `display` từ phần tử được giữ, **không được kỳ vọng nhất định nhận "Java" hay "JAVA"**.

Đây chỉ là đoạn mô tả hành vi; khi dùng record override `equals`/`hashCode`, cần bảo đảm hai phương thức nhất quán, và không dựa vào việc JVM giữ instance nào.

Nếu nghiệp vụ cần chọn phiên bản đại diện theo quy tắc rõ ràng (ví dụ ưu tiên tên xuất hiện đầu tiên, tên chuẩn hóa hoặc bản mới nhất), hãy **chọn đại diện bằng thuật toán riêng trước khi gọi `Set.copyOf`**. Tập hợp không tự quyết định chính sách ưu tiên nghiệp vụ.

## 3. Chuẩn hóa giá trị khác với loại trùng

### 3.1. Vì sao Set.copyOf trực tiếp chưa đủ?

~~~java
Set<String> raw = Set.copyOf(
        List.of(" Java ", "JAVA", "java"));
~~~

Ba chuỗi trong ví dụ **không bằng nhau theo `String.equals`**:

- `" Java "` có khoảng trắng.
- `"JAVA"` có chữ hoa.
- `"java"` có chữ thường.

Vì thế `raw.size()` sẽ là 3, không phải 1.

**Set không biết định nghĩa "giống nhau" của nghiệp vụ.** Nó chỉ áp dụng quy tắc equality của kiểu phần tử.

### 3.2. Chính sách chuẩn hóa được dùng trong bài

Một cách làm hợp lý cho **nhãn dùng để tìm kiếm/lọc, không phân biệt chữ hoa và thường**:

~~~text
raw value
  |
  +-- yêu cầu non-null
  |
  +-- strip() khoảng trắng ở hai đầu
  |
  +-- toLowerCase(Locale.ROOT)
  |
  +-- Normalizer.normalize(..., NFC)
  |
  +-- từ chối chuỗi rỗng/blank
  |
  v
canonical string
  |
  +-- tập hợp các canonical strings
  |
  v
Set.copyOf(...)
~~~

Mỗi bước phải tương thích nghiệp vụ:

- `String.strip()` (Java 11) sử dụng định nghĩa Unicode whitespace theo `Character.isWhitespace`; khác `String.trim()` ở một số mã ký tự. Ví dụ runnable Java 17+ dùng `strip()` để nhấn mạnh xử lý dữ liệu văn bản hiện đại.
- `toLowerCase(Locale.ROOT)` tránh phụ thuộc **default locale** của máy. Không phải mọi loại identifier cần lowercase; email, username, khóa truy cập hoặc mã case-sensitive có chính sách khác nhau.
- `Normalizer.Form.NFC` đưa những cách biểu diễn Unicode **tương đương chuẩn tắc** về dạng canonical composed. Nó **không loại bỏ dấu tiếng Việt**, không tự bảo vệ trước homoglyph spoofing, và không phải quy tắc tương đương ngôn ngữ cho mọi sản phẩm.
- Kiểm `isBlank()` sau chuẩn hóa nhằm loại những nhãn không có nội dung nếu nghiệp vụ yêu cầu.
- `Set.copyOf` được gọi **sau** các bước trên để gộp những canonical values bằng nhau.

**Không tự động dùng `NFKC`, bỏ mọi dấu tiếng Việt, bỏ dấu câu hoặc lower-case identifiers bảo mật** khi không có yêu cầu: những biến đổi đó có thể làm hai giá trị vốn khác nghĩa thành một.

### 3.3. Phân biệt normalization và validation

Normalization chuyển một giá trị có thể chấp nhận thành dạng chuẩn. Validation quyết định giá trị có hợp lệ không.

Ví dụ:

~~~text
" API "       -> "api"     (chuẩn hóa)
"Java"        -> "java"    (chuẩn hóa)
"java"        -> "java"    (trùng với giá trị trước)
"   "         -> lỗi       (chính sách từ chối blank)
null          -> lỗi       (không phải nhãn hợp lệ)
"admin;DROP"  -> cần kiểm theo policy
~~~

`Set.copyOf` **không xác thực an ninh** cho input. Nó không loại injection payload, không giới hạn độ dài chuỗi hoặc số phần tử, không xử lý allowlist và cũng không thay authorization.

Nếu nhãn được đưa vào SQL/HTML/command line/URL, dùng **parameterized query, escaping hoặc encoding đúng ngữ cảnh** ở bước xuất, tách khỏi công việc chuẩn hóa và gộp phần tử.

### 3.4. Unicode: hai chuỗi nhìn giống nhau nhưng byte khác nhau

~~~java
String composed = "Caf\u00e9";
String decomposed = "Cafe\u0301";

System.out.println(composed.equals(decomposed)); // false
~~~

Ký tự `é` có thể là một code point dựng sẵn hoặc chuỗi `e` cộng combining acute mark. `String.equals` so các ký tự bên trong, nên hai cách biểu diễn **không luôn bằng nhau trước NFC**.

Nếu policy cho phép coi chúng cùng một nhãn, áp `Normalizer.normalize(text, Normalizer.Form.NFC)` trước khi tạo tập:

~~~java
String a = java.text.Normalizer.normalize(
        composed, java.text.Normalizer.Form.NFC);
String b = java.text.Normalizer.normalize(
        decomposed, java.text.Normalizer.Form.NFC);
System.out.println(a.equals(b)); // true
~~~

Đây là lý do một quy trình canonicalization có thể gồm nhiều hơn chỉ `strip` và `toLowerCase`.

## 4. Một tập không chỉnh sửa được khác với một tập bất biến sâu

### 4.1. Unmodifiable collection

~~~java
Set<String> tags = Set.copyOf(
        List.of("api", "java"));

tags.add("streams"); // UnsupportedOperationException
~~~

Mọi phương thức thay đổi cấu trúc như `add`, `remove` và `clear` đều không được hỗ trợ bởi kết quả của `Set.copyOf`. Đây là **unmodifiable set**.

Không đồng nghĩa tất cả **object được chứa** đều bất biến. Nếu phần tử là object mutable, code giữ reference tới phần tử đó vẫn có thể sửa nội dung bên trong.

### 4.2. Set.copyOf chỉ là sao chép nông (shallow copy)

Giả sử:

~~~java
final class Box {
    int value;
    Box(int value) {
        this.value = value;
    }
}
~~~

Và:

~~~java
Box box = new Box(1);
Set<Box> frozen = Set.copyOf(List.of(box));

box.value = 2;
System.out.println(
        frozen.iterator().next().value); // 2
~~~

Tập không thể được thêm/xóa phần tử, nhưng instance `box` nằm bên trong vẫn là cùng object có field thay đổi được.

Trong ví dụ này `Box` dùng equality mặc định theo identity; thay `value` không đổi `equals`/`hashCode`. **Nếu phần tử mutable có fields được dùng để tính equals/hashCode rồi bạn sửa fields khi đang nằm trong Set, hành vi tập có thể trở nên không xác định**, kể cả những phép `contains`. Không dùng mutable hash keys làm phần tử tập có vòng đời dài.

### 4.3. Khi phần tử là String

`String` là immutable, nên `Set<String>` từ những canonical strings là một lựa chọn đơn giản: tập không đổi cấu trúc và mỗi phần tử không thể bị sửa nội dung tại chỗ.

Nhưng nếu phần tử là record chứa `List<String>` mutable, thì chỉ dùng record **không đủ** để đảm bảo bất biến sâu:

~~~java
record Group(String name, List<String> members) {
}
~~~

Record không tự sao chép `members`. Nếu cần snapshot an toàn:

~~~java
record Group(String name, List<String> members) {
    Group {
        java.util.Objects.requireNonNull(name);
        members = List.copyOf(members);
    }
}
~~~

Ở đây `List.copyOf` bảo vệ cấu trúc danh sách member; vì phần tử `String` cũng immutable, độ sâu bảo vệ cho ví dụ là phù hợp. Nếu member lại chứa đối tượng mutable, cần bảo vệ/clone ở tầng sâu hơn theo mô hình dữ liệu.

### 4.4. Nguồn đổi sau khi tạo tập

~~~java
var source = new ArrayList<>(
        List.of("java", "api"));
var frozen = Set.copyOf(source);

source.add("streams");
System.out.println(
        frozen.contains("streams")); // false
~~~

Đây là **snapshot cấu trúc**: thay `source` sau khi copy không thay thành viên của `frozen`. Không nhầm với một **unmodifiable view** trỏ vào collection cũ.

### 4.5. Trường hợp Set.copyOf có thể tái sử dụng object

Nếu truyền một `Set` đã không chỉnh sửa được:

~~~java
Set<String> first = Set.of("api", "java");
Set<String> second = Set.copyOf(first);
~~~

Implementation có thể không tạo thêm instance. **Không assert `first == second` hoặc `first != second`**: không phải điều kiện của contract.

Các unmodifiable sets được tạo bằng factory được coi là **value-based**; không dùng identity của kết quả làm khóa logic, và không dùng instance ấy như monitor khóa của `synchronized`. Dựa vào `equals` và dữ liệu thật của tập.

## 5. Không có thứ tự duyệt: ổn định ý nghĩa, không ổn định cách in

### 5.1. Đừng so Set.toString() với một chuỗi cố định

~~~java
Set<String> tags = Set.copyOf(
        List.of("z", "a", "m"));

System.out.println(tags); // Thứ tự không được bảo đảm
~~~

Bản JDK hoặc lần chạy khác có thể xuất hiện `[a, m, z]`, `[z, m, a]` hoặc thứ tự khác. Với những factory sets hiện đại, tài liệu Oracle cũng mô tả việc thứ tự duyệt có thể được thay đổi/ngẫu nhiên hóa để bộc lộ code phụ thuộc thứ tự.

**Tập giá trị không có thứ tự logic.** Thứ tự trong output phải do code quyết định ở một bước riêng.

### 5.2. Muốn thứ tự chữ cái cố định

~~~java
Set<String> tags = Set.copyOf(
        List.of("z", "a", "m"));

System.out.println(new TreeSet<>(tags));
// [a, m, z]
~~~

`TreeSet` duyệt theo natural ordering của `String`, nên phần hiển thị có thứ tự xác định theo ký tự. Đầu ra trên là đúng với các ký tự ASCII trong ví dụ.

Hoặc trả về danh sách đã sắp xếp:

~~~java
List<String> ordered = tags.stream()
        .sorted()
        .toList();
~~~

`Stream.toList()` xuất hiện từ Java 16 và trả danh sách không chỉnh sửa được; ví dụ của bài chọn Java 17+ nên dùng được. Nếu target Java 10, thay bằng cách sắp xếp trên một `ArrayList` sau khi copy; **không nhầm tính năng thêm sau Java 10 với API `Set.copyOf` vốn đã có từ Java 10**.

### 5.3. Muốn giữ thứ tự xuất hiện lần đầu

Nếu hợp đồng dữ liệu là “giữ thứ tự nhãn hợp lệ xuất hiện lần đầu”, `Set.copyOf` **không phải nơi bảo đảm thứ tự đó**. Có thể dùng:

~~~java
LinkedHashSet<String> ordered = new LinkedHashSet<>();
for (String raw : inputs) {
    ordered.add(normalizeToken(raw));
}

Set<String> view = Collections.unmodifiableSet(
        new LinkedHashSet<>(ordered));
~~~

`LinkedHashSet` duy trì thứ tự chèn. `Collections.unmodifiableSet` bọc một bản sao riêng nên, nếu không leak reference tới bản sao đó, caller không thể đổi cấu trúc qua view.

Không viết `Set.copyOf(ordered)` rồi kỳ vọng giữ insertion order: `Set.copyOf` không bảo đảm điều ấy.

**Trường hợp cần JSON array có thứ tự xác định:** thường chuyển thành `List` đã sắp xếp hoặc giữ thứ tự chèn theo yêu cầu; đừng dùng một Set không có order làm format chuẩn đầu ra.

## 6. So sánh các API Set phổ biến hiện nay

| API | Nguồn đầu vào | Gặp trùng | Cho sửa cấu trúc? | Thứ tự |
| --- | --- | --- | --- | --- |
| `Set.of("a", "b")` | Giá trị khai báo trực tiếp | Ném `IllegalArgumentException` nếu bằng nhau | Không | Không bảo đảm |
| `Set.copyOf(collection)` | Collection hiện có | Gộp, giữ đại diện bất kỳ | Không | Không bảo đảm |
| `new HashSet<>(collection)` | Collection hiện có | Gộp | Có | Không bảo đảm |
| `new LinkedHashSet<>(collection)` | Collection hiện có | Gộp | Có | Theo insertion order |
| `new TreeSet<>(collection)` | Collection hiện có | Gộp theo comparator/natural order | Có | Theo comparator |
| `Collections.unmodifiableSet(existing)` | Set hiện có | Do backing Set quyết định | Không qua view | Do backing Set |
| `Collectors.toUnmodifiableSet()` | Stream | Gộp, giữ đại diện bất kỳ | Không | Không bảo đảm |
| `List.copyOf(collection)` | Collection hiện có | **Không gộp** | Không | Theo vị trí nguồn |

### 6.1. Set.of là công cụ cho các hằng số đã biết

~~~java
Set<String> valid = Set.of("draft", "active", "closed");
~~~

Phù hợp khi tự code một tập hằng không trùng và không null. Có lợi khi duplicate là lỗi lập trình cần phát hiện ngay.

### 6.2. Set.copyOf là công cụ đóng băng dữ liệu đã xử lý

~~~java
var normalized = new ArrayList<String>();
// Một pipeline validation/normalization đã điền dữ liệu.
Set<String> result = Set.copyOf(normalized);
~~~

Phù hợp khi đầu vào là danh sách có thể trùng và muốn **tập kết quả không được sửa cấu trúc**.

### 6.3. Collections.unmodifiableSet có thể chỉ là một view

~~~java
var mutable = new HashSet<String>();
mutable.add("java");

Set<String> view =
        Collections.unmodifiableSet(mutable);

mutable.add("api");
System.out.println(view.contains("api")); // true
~~~

View không cho `view.add` nhưng vẫn phản ánh thay đổi của `mutable`. Đây là sự khác biệt quan trọng với snapshot cấu trúc mà `Set.copyOf` tạo từ collection mutable.

Nếu cần giữ insertion order nhưng vẫn muốn defensive copy, tạo bản `LinkedHashSet` **mới** rồi bọc nó trong unmodifiable view mà không công bố backing reference.

### 6.4. Set.copyOf không cần stream collector

Nếu đã có một collection cuối cùng:

~~~java
Set<String> immutable =
        Set.copyOf(normalizedValues);
~~~

thì không cần chuyển qua `stream().collect(Collectors.toSet())` rồi mới copy chỉ vì muốn dùng Stream API. Ngược lại, nếu toàn bộ xử lý đang là stream pipeline, có thể kết thúc bằng `Collectors.toUnmodifiableSet()` (Java 10), với cùng yêu cầu null/equals và không có thứ tự bảo đảm.

### 6.5. TreeSet không thay thế equality của Set.copyOf

`TreeSet` dùng comparator/natural ordering để quyết định hai phần tử có cùng một vị trí logic hay không. Nếu comparator **không nhất quán với equals**, cách nó gộp phần tử có thể khác `Set.copyOf`.

Do đó đừng dùng một `TreeSet<>(caseInsensitiveComparator)` để gộp xong rồi mong `Set.copyOf` tự phục hồi những giá trị đã bị comparator bỏ. Hãy chọn rõ **chính sách canonicalization** hoặc comparator/equality tương thích với contract nghiệp vụ trước.

## 7. Chương trình Java 17+ hoàn chỉnh: pipeline chuẩn hóa, snapshot và kiểm thử

Đây là ví dụ chạy độc lập, phù hợp với yêu cầu thực hành tổng hợp. Chương trình chứng minh:

- Chuẩn hóa `strip`, `toLowerCase(Locale.ROOT)` và Unicode NFC.
- `Set.copyOf` gộp duplicate theo `String.equals`.
- Nguồn `ArrayList` đổi sau khi copy không ảnh hưởng membership.
- Set không cho thêm phần tử.
- Collection chứa null bị từ chối.
- Nhãn rỗng/blank bị validation từ chối.
- `Set.of` khác `Set.copyOf` khi gặp duplicate.
- Thứ tự hiển thị được tạo bằng `TreeSet`, không dựa vào iteration order.
- Unmodifiable set không đồng nghĩa bất biến sâu nếu chứa object mutable.

Lưu tệp **`CanonicalTagsDemo.java`** theo UTF-8:

~~~java
import java.text.Normalizer;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;

public final class CanonicalTagsDemo {

    private CanonicalTagsDemo() {
    }

    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    static String normalizeToken(String raw) {
        Objects.requireNonNull(raw, "tag");

        String result = raw.strip()
                .toLowerCase(Locale.ROOT);
        result = Normalizer.normalize(
                result, Normalizer.Form.NFC);

        if (result.isBlank()) {
            throw new IllegalArgumentException("blank tag");
        }
        return result;
    }

    static Set<String> normalizeTags(
            Collection<String> rawTags) {

        Objects.requireNonNull(rawTags, "rawTags");

        List<String> normalized = new ArrayList<>();
        for (String raw : rawTags) {
            normalized.add(normalizeToken(raw));
        }
        return Set.copyOf(normalized);
    }

    static String stableOutput(Set<String> tags) {
        return new TreeSet<>(tags).toString();
    }

    public static void main(String[] args) {
        List<String> input = new ArrayList<>(
                List.of(
                        " Java ",
                        "JAVA",
                        " API ",
                        "api",
                        " Streams ",
                        "streams"));

        Set<String> tags = normalizeTags(input);

        System.out.println(
                "canonical=" + stableOutput(tags));
        System.out.println("count=" + tags.size());
        System.out.println(
                "containsJava="
                + tags.contains(normalizeToken("  JAVA  ")));
        System.out.println(
                "equalsSet="
                + tags.equals(Set.of("api", "java", "streams")));

        input.add("added-later");
        System.out.println("sourceSize=" + input.size());
        System.out.println(
                "snapshotUnaffected="
                + !tags.contains("added-later"));

        boolean mutationRejected = false;
        try {
            tags.add("extra");
        } catch (UnsupportedOperationException ex) {
            mutationRejected = true;
        }
        System.out.println(
                "mutationRejected=" + mutationRejected);

        Set<String> duplicateCopy = Set.copyOf(
                List.of("a", "a", "b"));
        System.out.println(
                "copyOfDuplicatesCollapsed="
                + (duplicateCopy.size() == 2));

        boolean ofDuplicateRejected = false;
        try {
            Set.of("a", "a");
        } catch (IllegalArgumentException ex) {
            ofDuplicateRejected = true;
        }
        System.out.println(
                "setOfDuplicateRejected="
                + ofDuplicateRejected);

        boolean nullRejected = false;
        try {
            Set.copyOf(Arrays.asList("a", null));
        } catch (NullPointerException ex) {
            nullRejected = true;
        }
        System.out.println("nullRejected=" + nullRejected);

        boolean blankRejected = false;
        try {
            normalizeTags(List.of("   "));
        } catch (IllegalArgumentException ex) {
            blankRejected = true;
        }
        System.out.println(
                "blankRejected=" + blankRejected);

        String composed = "Caf\u00e9";
        String decomposed = "Cafe\u0301";
        Set<String> accents = normalizeTags(
                List.of(composed, decomposed));
        System.out.println(
                "unicodeMerged=" + (accents.size() == 1));

        Box box = new Box(1);
        Set<Box> shallow = Set.copyOf(List.of(box));
        box.value = 2;
        System.out.println(
                "mutableElementVisible="
                + (shallow.iterator().next().value == 2));
    }
}
~~~

### 7.1. Biên dịch và chạy trên JDK 17+

~~~bash
javac --release 17 -encoding UTF-8 CanonicalTagsDemo.java
java CanonicalTagsDemo
~~~

**Stdout chính xác:**

~~~text
canonical=[api, java, streams]
count=3
containsJava=true
equalsSet=true
sourceSize=7
snapshotUnaffected=true
mutationRejected=true
copyOfDuplicatesCollapsed=true
setOfDuplicateRejected=true
nullRejected=true
blankRejected=true
unicodeMerged=true
mutableElementVisible=true
~~~

Vì chương trình chỉ in Set dưới dạng đã được `new TreeSet<>(tags)` sắp xếp và không in danh sách trực tiếp từ `Set.copyOf`, stdout ở trên **không phụ thuộc thứ tự duyệt Set**.

### 7.2. Giải thích kết quả theo từng bước

**canonical=[api, java, streams]**: sáu giá trị input đã chuẩn hóa thành ba canonical strings. `TreeSet` chỉ phục vụ hiển thị ổn định; bộ dữ liệu chính vẫn là `Set.copyOf` không chỉnh sửa được.

**count=3**: sau normalization, duplicate strings có `equals==true` được gộp.

**containsJava=true**: lookup `"  JAVA  "` cũng được đi qua `normalizeToken` trước khi gọi `contains`; nếu không chuẩn hóa khóa tra cứu thì có thể trả false sai với ý nghĩa nghiệp vụ.

**equalsSet=true**: `Set.equals` không phụ thuộc iteration order; hai set có cùng các phần tử được xem là bằng nhau.

**sourceSize=7 / snapshotUnaffected=true**: thay source list sau khi tạo snapshot không thêm giá trị vào `tags`.

**mutationRejected=true**: lệnh `tags.add("extra")` ném `UnsupportedOperationException`, được bắt và chuyển thành giá trị kiểm chứng.

**copyOfDuplicatesCollapsed=true**: hai chuỗi `"a"` được gộp thành một; `Set.copyOf` không coi duplicate là lỗi.

**setOfDuplicateRejected=true**: `Set.of("a", "a")` là lời gọi factory có duplicate literal và ném `IllegalArgumentException`.

**nullRejected=true**: `Arrays.asList("a", null)` là một collection hợp lệ chứa null; `Set.copyOf` từ chối nó.

**blankRejected=true**: đây là **chính sách của `normalizeToken`**, không phải cơ chế tự động của `Set.copyOf`. Một chuỗi `""` hoặc `"   "` không phải null và vẫn có thể là phần tử Set nếu code không tự từ chối.

**unicodeMerged=true**: hai cách biểu diễn chữ `é` trước NFC được đưa về cùng dạng chuẩn, nên Set gộp.

**mutableElementVisible=true**: tập không cho thêm/xóa `Box` nhưng không đóng băng `box.value`. Đây là ví dụ giải thích giới hạn shallow immutability.

### 7.3. Những điều ví dụ cố tình không làm

- Không đo timing/performance vì không có ngưỡng cố định đúng cho mọi JVM.
- Không dựa vào class implementation nội bộ của tập (ví dụ `ImmutableCollections.SetN`).
- Không xét object identity của kết quả copy.
- Không suy order từ `hashCode` hay JDK version.
- Không dùng API không công khai hoặc cấu hình JVM cũ đã legacy.
- Không coi normalization đồng nghĩa với xác thực dữ liệu bảo mật.
- Không lấy ngẫu nhiên dữ liệu hoặc truy cập mạng/đồng hồ, nên stdout kiểm được bằng mắt và CI.

## 8. Đưa pipeline vào ứng dụng: value object và defensive copy

### 8.1. Đặt quy tắc tại boundary

Một hướng thiết kế rõ ràng là chỉ cho lớp ứng dụng truy cập **canonical Set<String>** qua một factory/service:

~~~java
static Set<String> canonicalize(
        Collection<String> source) {
    // Kiểm input và normalize từng phần tử.
    List<String> normalized = new ArrayList<>();
    for (String item : Objects.requireNonNull(source)) {
        normalized.add(normalizeToken(item));
    }
    return Set.copyOf(normalized);
}
~~~

**Đây là đoạn minh họa bên trong một class có các imports và phương thức `normalizeToken` như chương trình đầy đủ ở mục 7.** Nó không phải ví dụ chạy độc lập.

Phân tách boundary giúp các phần còn lại của ứng dụng có thể tin tưởng những bất biến:

~~~text
tags != null
không có null members
không có blank members
mọi member là canonical string
không có duplicate theo equals
không thể thêm hoặc xóa member từ bên ngoài
~~~

Nhưng cần bảo đảm mọi đầu vào tạo entity đều đi qua boundary đó. Nếu nơi khác tự dùng `Set.copyOf(raw)` mà bỏ normalization, hệ thống có thể lưu những tập “không sửa được nhưng chưa chuẩn”.

### 8.2. Constructor của record có thể defensive copy

Ví dụ thiết kế dữ liệu bất biến ở mức cấu trúc:

~~~java
record SearchOptions(Set<String> tags) {
    SearchOptions {
        tags = Set.copyOf(
                Objects.requireNonNull(tags));
    }
}
~~~

Compact constructor gán lại tham số `tags`; record lưu giá trị đã defensive-copy, không giữ reference tới một mutable set mà caller có thể sửa cấu trúc. Tuy nhiên:

- Constructor này **chỉ copy**, không thực hiện lowercase/strip/Unicode normalization.
- Nếu muốn canonical strings, nên truyền tập đã chuẩn hóa từ một factory rõ ràng.
- Một bản Set không chỉnh sửa được chứa objects mutable vẫn có vấn đề shallow immutability.
- Record có thể chứa reference tới một value-based Set được JVM reuse; đừng dùng identity của nó như khóa business.

### 8.3. Cập nhật tập theo phong cách copy-on-write

Khi Set đã unmodifiable, không thể gọi `tags.add("new")` để thay đổi nó.

Một cách an toàn là tạo **tập mới**:

~~~java
Set<String> current =
        Set.of("api", "java");

Set<String> nextMutable = new HashSet<>(current);
nextMutable.add("streams");

Set<String> next = Set.copyOf(nextMutable);
~~~

`current` không đổi; `next` chứa ba phần tử. Đây là kiểu cập nhật thích hợp khi trạng thái thay đổi không thường xuyên hoặc muốn giữ các snapshots riêng.

Với workload cập nhật liên tục và kích thước tập rất lớn, copy toàn bộ mỗi lần có thể tốn kém. Khi đó dùng mutable set được bảo vệ bởi cơ chế đồng bộ phù hợp, hoặc cấu trúc persistent data structure chuyên dụng; chỉ tạo immutable snapshot ở boundary cần thiết.

### 8.4. Tại sao không đưa Set.copyOf vào mọi vòng lặp?

Sai về hiệu năng nếu không cần snapshot mỗi bước:

~~~java
Set<String> current = Set.of();
for (String value : incoming) {
    Set<String> changed = new HashSet<>(current);
    changed.add(normalizeToken(value));
    current = Set.copyOf(changed);
}
~~~

Với nhiều phần tử, quy trình tạo liên tục những bản set trung gian không cần thiết. Thường tốt hơn:

~~~java
Set<String> working = new HashSet<>();
for (String value : incoming) {
    working.add(normalizeToken(value));
}
Set<String> frozen = Set.copyOf(working);
~~~

Như vậy chỉ đóng băng **một lần khi đã xây dựng xong**. Code sử dụng `Set.copyOf` để xác định ownership và mutability boundary, không như một phép làm đẹp cú pháp lặp lại.

## 9. Khi dữ liệu trùng là lỗi, không được gộp âm thầm

### 9.1. Gộp nhãn tìm kiếm và kiểm định ID khác nhau

Nhãn tìm kiếm:

~~~text
" Java ", "java", "JAVA"
=> "java" là kết quả mong muốn.
~~~

Danh sách **mã định danh được yêu cầu duy nhất**:

~~~text
"acct-001", "acct-001"
=> có thể phải báo lỗi "duplicate account ID".
~~~

Nếu business rule yêu cầu **phát hiện** duplicate, `Set.copyOf` vẫn tạo một Set duy nhất và **không báo lỗi**. Vì vậy phải kiểm trước khi tạo tập hoặc so sánh với quy tắc cardinality rõ ràng.

Ví dụ kiểm duplicate sau normalize:

~~~java
List<String> normalized = raw.stream()
        .map(CanonicalTagsDemo::normalizeToken)
        .toList();

Set<String> unique = Set.copyOf(normalized);

if (unique.size() != normalized.size()) {
    throw new IllegalArgumentException(
            "duplicate normalized values");
}
~~~

Đây là đoạn code minh họa nằm trong phạm vi class nơi đã định nghĩa `normalizeToken` và imports thích hợp. Với dữ liệu lớn, nếu cần báo **phần tử nào trùng**, hãy dùng `Map<String, ...>` để ghi vị trí/nguồn của từng canonical key.

**Độ dài khác nhau** sau khi Set.copyOf được tạo cho biết đã có duplicate theo equality. Nhưng để báo xung đột chính xác, cần preserve metadata đầu vào trước khi gộp.

### 9.2. Chọn đại diện có ý nghĩa

Giả sử cùng một `id` có nhiều display labels. Nếu ưu tiên tên đầu tiên, dùng logic như:

~~~java
Map<String, String> firstDisplay = new LinkedHashMap<>();
for (String original : rawLabels) {
    String key = normalizeToken(original);
    firstDisplay.putIfAbsent(key, original);
}
Set<String> keys = Set.copyOf(firstDisplay.keySet());
~~~

`putIfAbsent` quy định rõ giữ value đầu tiên cho mỗi canonical key. `Set.copyOf` cuối cùng chỉ đóng băng **tập khóa**; nó không tự chọn display label.

Cần xác định xử lý các trường hợp null/blank và quyền sở hữu mutable values trước khi triển khai thật. Và nếu cần giữ thứ tự các khóa như nguồn, đừng chuyển sang `Set.copyOf` để kỳ vọng thứ tự; có thể công bố ordered list riêng.

### 9.3. Case folding không phải giải pháp bảo mật tổng quát

`toLowerCase(Locale.ROOT)` là lựa chọn hợp lý cho ví dụ tags không phân biệt hoa/thường, nhưng không tự bảo đảm hai tên người dùng có nghĩa tương đương về ngôn ngữ hoặc ngăn Unicode confusables.

Với thông tin đăng nhập, domain names quốc tế hóa, file paths hay IDs phân biệt chữ hoa/thường, policy phải được định nghĩa riêng và kiểm theo tiêu chuẩn domain. Không copy nguyên pipeline tags cho mọi loại dữ liệu.

## 10. Đồng bộ hóa, thread safety và chia sẻ dữ liệu

### 10.1. Dùng Set.copyOf để công bố cấu hình chỉ đọc

Một tập nhãn immutable cấu trúc, chứa các `String` immutable, thích hợp làm dữ liệu shared read-only sau khi được công bố an toàn giữa các threads.

~~~java
final class ServiceSettings {
    private final Set<String> enabledFeatures;

    ServiceSettings(Collection<String> raw) {
        enabledFeatures = Set.copyOf(raw);
    }

    Set<String> enabledFeatures() {
        return enabledFeatures;
    }
}
~~~

Đoạn này minh họa cấu trúc, không bao gồm imports/validation. Bản Set không thể bị caller đổi cấu trúc qua reference được trả.

Nhưng **safe publication** của object chứa nó vẫn phải đúng nguyên tắc Java Memory Model. `Set.copyOf` không thay `volatile`, `final` publication, synchronization hoặc concurrent update coordination nếu settings object được thay thế khi nhiều threads đang chạy.

### 10.2. Nếu cấu hình thay đổi tại runtime

Có thể dùng pattern tạo snapshot mới rồi thay reference theo cơ chế an toàn:

~~~java
private volatile Set<String> activeTags = Set.of();

void replaceTags(Collection<String> newRaw) {
    Set<String> next = normalizeTags(newRaw);
    activeTags = next;
}
~~~

Đoạn này nằm trong một class có `normalizeTags` phù hợp. Một thread đọc `activeTags` sẽ thấy **một snapshot Set hoàn chỉnh**, thay vì collection bị sửa từng phần trong lúc đang duyệt.

Nếu cập nhật dựa trên trạng thái cũ và cần tránh mất cập nhật từ nhiều writers, chỉ `volatile` là chưa đủ để cung cấp atomic read-modify-write: có thể cần `AtomicReference`/CAS, khóa hoặc transaction.

### 10.3. Không sửa collection nguồn đồng thời khi copy

`Set.copyOf` không phải cơ chế chụp snapshot nguyên tử của một collection đang bị thread khác sửa không đồng bộ. Nếu `ArrayList` nguồn bị thay đổi trong khi đang iterate/copy, có thể có lỗi concurrency hoặc dữ liệu không nhất quán tùy implementation.

Cần tạo một snapshot được đồng bộ đúng, khóa nguồn hoặc dùng cấu trúc/concurrency contract phù hợp. Khi đã có một unmodifiable set chứa phần tử immutable, nhiều readers có thể sử dụng thuận tiện.

### 10.4. Tránh khóa theo factory Set

Các factory collections có đặc tính **value-based**; không dựa vào identity hay `synchronized(set)` trên một instance `Set.copyOf` như monitor chung của ứng dụng. Dùng lock object có identity ổn định hoặc một primitive synchronization rõ ràng.

## 11. Kiểm thử tập chuẩn hóa: bất biến thay vì thứ tự

### 11.1. Kiểm các ca quan trọng

| Đầu vào | Kết quả mong đợi |
| --- | --- |
| `List.of()` | Set rỗng, unmodifiable |
| `["a", "a", "b"]` | Hai giá trị `a`, `b` |
| `[" Java ", "JAVA"]` với normalization | Một `java` |
| `["Café", "Cafe\\u0301"]` với NFC | Một canonical `café` |
| Collection chứa null | `NullPointerException` hoặc lỗi domain đã định nghĩa |
| Nhãn chỉ có whitespace | `IllegalArgumentException` nếu policy cấm |
| Nguồn bị thêm phần tử sau copy | Snapshot không thay membership |
| Cố gọi `result.add(...)` | `UnsupportedOperationException` |
| Kết quả được in theo thứ tự | Chỉ ổn định sau khi sort |
| Phần tử mutable bị sửa | Nội dung phần tử có thể đổi; không phải deep immutable |

### 11.2. Viết assertions không phụ thuộc thứ tự

Nên:

~~~java
Set<String> actual = Set.copyOf(
        List.of("b", "a", "b"));

assert actual.equals(Set.of("a", "b"));
assert actual.size() == 2;
~~~

Không nên:

~~~java
assert actual.toString().equals("[a, b]");
~~~

Một JVM có thể duyệt theo thứ tự khác. **Đặc biệt trong CI**, đừng để test chỉ chạy được trên máy developer vì hash seed/iteration order tình cờ giống.

### 11.3. Test chuẩn hóa có tính idempotent

Một canonicalization function tốt thường nên thỏa:

~~~text
normalize(normalize(x)) == normalize(x)
~~~

theo equality, đối với giá trị hợp lệ thuộc domain đã định nghĩa. Có thể test:

~~~java
String first = normalizeToken("  Java ");
String second = normalizeToken(first);
System.out.println(first.equals(second)); // true
~~~

Thao tác `Set.copyOf` cũng ổn định về **giá trị set** khi áp lại cho một unmodifiable set:

~~~java
Set<String> first = Set.copyOf(values);
Set<String> again = Set.copyOf(first);
System.out.println(first.equals(again)); // true
~~~

Nhưng không assert hai references `first == again`. Implementation có thể reuse hoặc tạo instance khác.

### 11.4. Test representative selection khi phần tử khác identity

Nếu hai objects có `equals==true` nhưng những fields khác nhau vẫn được giữ, `Set.copyOf` có thể chọn đại diện bất kỳ. Không viết test yêu cầu nó giữ bản đầu hay bản cuối.

Muốn deterministic, trước tiên dùng `LinkedHashMap`, comparator với tie-breaker đầy đủ hoặc một policy khác đã định nghĩa. Rồi test **policy đó**, không test incidental behavior của Set factory.

### 11.5. Bài test hiệu năng phải thực tế

Không nêu ngưỡng “Set.copyOf luôn nhanh hơn HashSet 2 lần”. JVM optimization, data size, load factor, allocation patterns và value types ảnh hưởng benchmark.

Để so performance, dùng công cụ benchmark thích hợp (ví dụ JMH), warmup, nhiều forks và workload đại diện. Khi gọi `copyOf` một lần ở boundary, tối ưu sớm hiếm khi quan trọng hơn **đúng ngữ nghĩa dữ liệu và ownership**.

## 12. Lỗi thường gặp khi dùng Set.copyOf

| Lỗi | Tại sao sai | Cách sửa |
| --- | --- | --- |
| Nghĩ `Set.copyOf` tự trim/lowercase | Chỉ xử lý Set theo equality | Chuẩn hóa trước |
| Dùng `Set.copyOf(raw)` cho IDs case-insensitive | `String.equals` phân biệt hoa/thường | Định nghĩa canonical key |
| Nghĩ duplicate sẽ ném `IllegalArgumentException` | Đó là khác biệt với `Set.of` | Kiểm duplicate riêng nếu cần |
| Truyền list có null rồi mong bỏ qua | Null bị từ chối | Validate/filter có chủ đích |
| Dùng `List.of("a", null)` để test copyOf | List.of ném lỗi trước | Dùng collection cho phép null |
| In thẳng Set và so chuỗi có thứ tự | Iteration order không được đảm bảo | Sort/ordered list riêng |
| Trông chờ giữ thứ tự LinkedHashSet | CopyOf không giữ contract ordering | Giữ ordered data structure khác |
| Nghĩ unmodifiable là deep immutable | Elements vẫn có thể mutable | Dùng immutable elements/deep copy |
| Sửa fields tham gia hashCode sau khi đưa vào Set | Phá invariants của Set | Không mutate keys |
| Cho rằng copyOf luôn tạo instance mới | Có thể reuse unmodifiable Set | Không so reference identity |
| Sử dụng Set factory làm monitor khóa | Value-based identity không ổn định | Lock object riêng |
| Bọc mutable source rồi gọi unmodifiableSet và coi là snapshot | Wrapper là view | Defensive-copy backing |
| Gọi Set.copyOf ở mỗi vòng lặp thêm dữ liệu | Cấp phát không cần thiết | Build mutable, freeze một lần |
| Chỉ kiểm nguồn theo `contains(rawInput)` | Lookup chưa normalize | Normalize query trước |
| Dùng NFKC/lowercase cho tất cả IDs | Có thể đổi semantics | Policy theo domain |
| Dùng normalize như biện pháp chống injection | Không thay validation/escaping | Xử lý an ninh theo ngữ cảnh |
| Gộp duplicate khi yêu cầu phải báo lỗi | Mất thông tin xung đột | Validate trước khi gộp |
| Chọn display label từ đại diện bất kỳ | Set không bảo đảm representative | Tách key và display policy |
| Sửa source đồng thời khi copy | Không có snapshot nguyên tử | Đồng bộ/kiểm concurrency |
| Khẳng định Java 10 có `String.strip` | `strip` từ Java 11 | Demo Java 17+ hoặc chọn API hợp target |
| Khẳng định `Set.copyOf` từ Java 9 | `Set.copyOf` được thêm Java 10 | Xem Javadoc Since |
| Dùng class nội bộ của Set factory | Không có API ổn định | Lập trình với interface `Set` |

## 13. Quy trình triển khai cho hệ thống thực

### Bước 1 — Xác định danh tính và policy

Một tập **tên nhãn tìm kiếm** có thể không phân biệt hoa/thường, nhưng tập **mã sản phẩm** có thể phân biệt. Viết rõ:

- Được phép null không?
- Chuỗi blank có hợp lệ không?
- Trim hay strip, có preserve whitespace bên trong không?
- Có phân biệt hoa/thường không?
- Unicode NFC/NFKC hay giữ nguyên?
- Có giới hạn số phần tử, độ dài mỗi giá trị không?
- Trùng lặp là hành vi hợp lệ hay lỗi dữ liệu?
- Cần giữ thứ tự hiển thị không?

### Bước 2 — Chuẩn hóa từng giá trị

Viết hàm normalization **thuần**, dễ test, không phụ thuộc default locale/clock/network. Chỉ chuyển đổi những gì contract cho phép. Có thể dùng `String.strip()`, `Locale.ROOT` và `Normalizer.Form.NFC` như demo, nhưng đừng copy mù quáng sang domain khác.

### Bước 3 — Validate dữ liệu sau normalize

Kiểm rỗng, độ dài, ký tự cho phép, allowlist, quyền truy cập hoặc cấu trúc liên quan. Đừng lầm việc chuỗi đã lowercase với việc được chấp nhận bởi business policy.

### Bước 4 — Quyết định chính sách duplicate

- Nếu duplicate được phép: tạo Set với `Set.copyOf`.
- Nếu duplicate là lỗi: phát hiện và báo trước khi làm mất dấu vết.
- Nếu duplicate cần merge: viết merge policy và canonical representative rõ ràng, dùng `Map.merge` hoặc thuật toán tương đương.
- Nếu cần giữ thứ tự đầu tiên: lưu danh sách/tập có ordered contract riêng.

### Bước 5 — Freeze và công bố kết quả

Khi dữ liệu đã hợp lệ, dùng:

~~~java
Set<String> canonical = Set.copyOf(normalized);
~~~

Với strings immutable, đây là dữ liệu read-only phù hợp cho configuration, filter options hoặc cache keys. Công bố an toàn giữa các threads nếu có chia sẻ.

### Bước 6 — Xuất dữ liệu có thứ tự khi cần

~~~java
List<String> sorted = canonical.stream()
        .sorted()
        .toList();
~~~

Dùng sorted list cho serializing array, snapshot test hoặc báo cáo. Không dựa vào `Set.toString()` trực tiếp.

### Bước 7 — Test và quan sát trong production

Kiểm số phần tử trước/sau normalize, tỉ lệ duplicate, số giá trị invalid, lượng dữ liệu đầu vào, nhưng tránh ghi thông tin nhạy cảm vào logs. Kiểm regressions khi policy normalization thay đổi, nhất là Unicode, case sensitivity và các identifiers từng được lưu theo format cũ.

## 14. Câu hỏi ôn tập

**Câu 1.** `Set.copyOf` ra mắt từ Java nào?

**Đáp án:** Java 10; vẫn được JDK hiện đại hỗ trợ.

**Câu 2.** `Set.copyOf(List.of("a","a"))` ném lỗi duplicate không?

**Đáp án:** Không. Kết quả chứa một phần tử `"a"`.

**Câu 3.** `Set.of("a","a")` thì sao?

**Đáp án:** Ném `IllegalArgumentException` vì các phần tử được cung cấp bị trùng.

**Câu 4.** `Set.copyOf` có tự bỏ null không?

**Đáp án:** Không. Collection null hoặc chứa phần tử null sẽ gây `NullPointerException`.

**Câu 5.** Vì sao `" Java "` và `"JAVA"` không được Set tự gộp?

**Đáp án:** Vì `String.equals` phân biệt khoảng trắng và chữ hoa/thường. Cần chuẩn hóa theo policy trước.

**Câu 6.** Vì sao dùng `Locale.ROOT`?

**Đáp án:** Để lowercasing không phụ thuộc locale mặc định của máy đối với policy ngôn ngữ trung lập như tags; không thay thế chính sách domain cụ thể.

**Câu 7.** NFC có tác dụng gì?

**Đáp án:** Chuẩn hóa những biểu diễn Unicode tương đương chuẩn tắc, ví dụ `é` dựng sẵn và `e` + combining acute; không tự loại bỏ dấu hay chống homoglyph spoofing.

**Câu 8.** Nếu thêm phần tử vào mutable source sau copy thì result có đổi không?

**Đáp án:** Không đổi **membership cấu trúc** của tập kết quả.

**Câu 9.** Nếu sửa field mutable bên trong phần tử Set thì sao?

**Đáp án:** Nội dung object vẫn có thể đổi; tập là shallow unmodifiable, không phải deep immutable. Không mutate fields tham gia equality/hashCode khi phần tử còn trong Set.

**Câu 10.** Có nên kiểm `result.toString().equals("[a, b]")` không?

**Đáp án:** Không, vì thứ tự Set factory không được đảm bảo; hãy so `equals` hoặc sắp xếp trước khi xuất.

**Câu 11.** `Set.copyOf` có luôn tạo object Set mới không?

**Đáp án:** Không. Implementation có thể reuse một unmodifiable set; không dựa vào `==`.

**Câu 12.** `Collections.unmodifiableSet(mutable)` có giống snapshot `Set.copyOf(mutable)` không?

**Đáp án:** Không. Wrapper đầu tiên là một view của mutable backing; thay đổi source có thể hiện qua view. `Set.copyOf` cho snapshot cấu trúc.

**Câu 13.** Nếu duplicate là lỗi business, có thể chỉ dùng copyOf rồi im lặng không?

**Đáp án:** Không. Cần validate duplicates theo quy tắc trước khi gộp hoặc phát hiện và báo thông tin xung đột.

**Câu 14.** Với dữ liệu cần giữ thứ tự thêm, có nên chọn `Set.copyOf` không?

**Đáp án:** Không để bảo đảm thứ tự. Dùng `LinkedHashSet`/ordered list với ownership thích hợp hoặc xuất danh sách được sắp xếp.

**Câu 15.** `String.strip()` thuộc Java 10 không?

**Đáp án:** Không. Nó được thêm từ Java 11. Vì vậy chương trình demo nhắm Java 17+ dù API cốt lõi `Set.copyOf` từ Java 10.

**Câu 16.** Muốn cập nhật Set unmodifiable thì làm gì?

**Đáp án:** Tạo mutable copy, áp cập nhật, rồi `Set.copyOf` lần nữa để tạo snapshot tiếp theo; cân nhắc chi phí nếu cập nhật thường xuyên.

## 15. Checklist kết thúc bài thực hành

### Đúng dữ liệu

- [ ] Nêu rõ định nghĩa “hai giá trị là trùng”.
- [ ] Chuẩn hóa trước khi Set.copyOf khi cần.
- [ ] Không dựa vào default locale cho tags trung lập.
- [ ] Chỉ áp Unicode normalization được business policy cho phép.
- [ ] Validate null, blank, giới hạn số lượng/kích thước.
- [ ] Phân biệt duplicate cần gộp và duplicate cần báo lỗi.
- [ ] Không dùng normalization thay cho input security controls.

### Đúng collection semantics

- [ ] Biết Set.copyOf từ Java 10 và Set.of từ Java 9.
- [ ] Biết copyOf gộp duplicate, còn of từ chối duplicate.
- [ ] Biết Set.copyOf từ chối null.
- [ ] Không khẳng định thứ tự duyệt.
- [ ] Không nhầm unmodifiable với deep immutable.
- [ ] Không assume output luôn là một instance khác.
- [ ] Không mutate fields tham gia hashCode/equals của phần tử.
- [ ] Không dùng factory Set làm monitor khóa.
- [ ] Biết khác biệt snapshot vs unmodifiable view.

### Đúng kiểm chứng và triển khai

- [ ] Java file và public class trùng tên.
- [ ] Biên dịch với `javac --release 17` trong ví dụ.
- [ ] Stdout chỉ dùng sorted Set hoặc boolean, không phụ thuộc iteration order.
- [ ] Test trực tiếp duplicate, null, blank, source mutation và mutator exception.
- [ ] Test Unicode canonical equivalence nếu policy cần.
- [ ] Lookup input cũng đi qua normalization.
- [ ] Có kế hoạch xử lý duplicate collision có ý nghĩa nghiệp vụ.
- [ ] Nếu cấu hình thay đổi runtime, công bố snapshot mới an toàn.
- [ ] Dùng dữ liệu/benchmark đại diện thay vì giả định performance.
- [ ] Không đưa API nội bộ/đã legacy vào implementation.

## 16. Tài liệu chính thức và nguồn tham khảo hiện hành

- [Oracle Java SE 25 — Set.copyOf(Collection)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Set.html#copyOf(java.util.Collection)): API contract, duplicate representative, null, unmodifiable, source independence và `Since: 10`.
- [Oracle Java SE 17 — Set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html): Set equality, value-based unmodifiable sets, không bảo đảm iteration order.
- [Oracle Java SE 25 — Creating Unmodifiable Lists, Sets, and Maps](https://docs.oracle.com/en/java/javase/25/core/creating-immutable-lists-sets-and-maps.html): khác biệt copyOf, factory collections, unmodifiable view, mutable elements và randomized iteration.
- [Dev.java — Creating and Processing Data with Collections Factory Methods](https://dev.java/learn/api/collections-and-streams/collections-framework/factory-methods/): mô tả `Set.copyOf` và `List.copyOf` từ Java 10.
- [Oracle Java SE 17 — java.text.Normalizer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html): NFC/NFD/NFKC/NFKD và chuẩn hóa Unicode.
- [Oracle Java SE 17 — String.strip()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#strip()): xử lý whitespace và `Since: 11`.
- [Oracle Java SE 17 — String.toLowerCase(Locale)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#toLowerCase(java.util.Locale)): locale-aware case mapping.
- [Oracle Java SE 17 — Locale.ROOT](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html#ROOT): locale gốc dùng cho xử lý không gắn văn hóa cụ thể.
- [Oracle Java SE 17 — LinkedHashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html): bảo đảm iteration order theo thứ tự chèn.
- [Oracle Java SE 17 — Collections.unmodifiableSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableSet(java.util.Set)): unmodifiable view khác structural snapshot.
- [Oracle Java SE 17 — Collectors.toUnmodifiableSet()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#toUnmodifiableSet()): collector tạo unmodifiable set và xử lý duplicate.
- [Oracle Java SE 17 — Stream.toList()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toList()): tạo unmodifiable list, có từ Java 16.
- [OpenJDK JEP 269 — Convenience Factory Methods for Collections](https://openjdk.org/jeps/269): nền tảng factory unmodifiable collections từ Java 9.

**Tổng kết:** `Set.copyOf` là công cụ Java 10 **đóng băng một tập giá trị đã được chuẩn bị**. Nó nhận `Collection`, loại các phần tử trùng theo `equals`, từ chối null, không cho sửa cấu trúc và **không cam kết thứ tự duyệt**. Nó **không tự tạo canonical representation**, không biến phần tử mutable thành immutable và không đảm bảo duplicate đại diện nào được giữ. Cách làm đúng là **định nghĩa policy → validate/normalize từng giá trị → chọn chiến lược duplicate → Set.copyOf → sắp xếp riêng nếu cần output có thứ tự → test các bất biến**.