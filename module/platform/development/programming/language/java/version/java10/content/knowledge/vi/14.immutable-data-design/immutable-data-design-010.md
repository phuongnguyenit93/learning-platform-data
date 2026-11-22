# Kiểm thử sự độc lập giữa nguồn và kết quả khi thiết kế dữ liệu chỉ đọc trong Java

> **Chủ đề Java 10 — Thiết kế dữ liệu chỉ đọc.** Bài hướng dẫn kiểm chứng rằng collection được công bố dưới dạng **snapshot** không thay đổi cấu trúc khi collection nguồn bị sửa về sau, phân biệt snapshot với **unmodifiable live view**, kiểm tra defensive copying tại ranh giới API và phát hiện giới hạn của sao chép nông. Các API `List.copyOf`, `Set.copyOf`, `Map.copyOf` và `Collectors.toUnmodifiable*` có từ Java 10, vẫn áp dụng trên các JDK hiện đại được hỗ trợ. Không yêu cầu sử dụng runtime Java 10 đã cũ.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **độc lập khỏi nguồn** có nghĩa gì đối với **thành viên và ánh xạ** trong `List`, `Set` và `Map`; không nhầm với “deep immutable”.
2. Thiết kế kiểm thử theo trình tự **chuẩn bị nguồn → tạo kết quả → thay đổi nguồn → đối chiếu cả hai** thay vì chỉ kiểm tra giá trị trước khi sửa.
3. Phân biệt **snapshot unmodifiable** tạo bằng `copyOf` với **unmodifiable view** tạo bằng `Collections.unmodifiableList/Set/Map`.
4. Kiểm tra cả hai hợp đồng độc lập: **không sửa được kết quả** và **sửa nguồn không làm đổi cấu trúc kết quả**.
5. Viết test không phụ thuộc thứ tự duyệt `Set/Map`, object identity, thông báo exception hoặc implementation cụ thể.
6. Phát hiện aliasing ở **phần tử mutable** và **collection lồng nhau**; thực hiện defensive copy đủ sâu theo hợp đồng miền.
7. Kiểm thử constructor/getter trả dữ liệu chỉ đọc, duplicate và null hợp lệ hoặc không hợp lệ, đồng thời hiểu giới hạn của test trong môi trường có nhiều thread.
8. Chạy được chương trình độc lập với **19 phép kiểm tra và thông báo lỗi rõ ràng** trên JDK hiện đại.

## 2. Định nghĩa đúng phạm vi “độc lập”

### 2.1. Snapshot khác live view

Một ví dụ ngắn:

```java
// Các dòng nằm trong một phương thức.
var source = new java.util.ArrayList<>(
        java.util.List.of("A", "B"));

var snapshot = java.util.List.copyOf(source);
var view = java.util.Collections.unmodifiableList(source);

source.add("C");

System.out.println(snapshot); // [A, B]
System.out.println(view);     // [A, B, C]
```

- `snapshot` có các phần tử đang có **tại thời điểm `copyOf`**. Việc thêm/xóa/thay thành viên của `source` về sau không phản ánh vào `snapshot`.
- `view` **không cho sửa qua chính view**, nhưng mọi thao tác đọc từ view “đọc xuyên qua” collection gốc. `source.add("C")` khiến `view` nhìn thấy `C`.
- Cả `snapshot.add("D")` và `view.add("D")` đều không được hỗ trợ và ném `UnsupportedOperationException`. Vì vậy **chỉ kiểm tra exception từ `add` là chưa đủ** để chứng minh nguồn và kết quả độc lập.

Đây là hai yêu cầu tách biệt:

1. **Unmodifiable:** caller không thể sửa collection qua tham chiếu kết quả.
2. **Independent snapshot:** caller hoặc thành phần khác sửa collection nguồn về sau không làm thay đổi **cấu trúc** kết quả đã nhận.

`Collections.unmodifiableList(source)` đáp ứng điều thứ nhất nhưng **không đáp ứng điều thứ hai** khi backing list còn bị sửa. `List.copyOf(source)` đáp ứng cả hai ở mức **thành viên list**, với điều kiện nguồn ổn định trong quá trình tạo snapshot.

### 2.2. Độc lập cấu trúc không đồng nghĩa bất biến sâu

Nếu danh sách chứa các đối tượng có thể sửa:

```java
var builder = new StringBuilder("v1");
var source = java.util.List.of(builder);
var snapshot = java.util.List.copyOf(source);

builder.append("-v2");
System.out.println(snapshot.get(0)); // v1-v2
```

`snapshot` không thay phần tử ở vị trí 0, nhưng chính **đối tượng `StringBuilder`** mà phần tử trỏ tới đã đổi trạng thái. `copyOf` **không deep-copy** phần tử. Kiểm thử phải phân biệt:

| Thuộc tính cần kiểm chứng | Ví dụ kỳ vọng | `List.copyOf` trực tiếp bảo đảm? |
| --- | --- | --- |
| Thêm phần tử vào nguồn sau `copyOf` | Snapshot không xuất hiện phần tử mới | Có |
| Xóa phần tử khỏi nguồn | Snapshot vẫn có thành viên cũ | Có |
| `set(index,newElement)` trên nguồn | Snapshot vẫn giữ tham chiếu phần tử cũ | Có |
| Gọi `add/set/remove` trên snapshot | Ném `UnsupportedOperationException` | Có |
| Thay đổi **trạng thái** phần tử mutable đã được copy | Không nhìn thấy trạng thái mới | **Không** |
| Một map value là `List` mutable bị sửa | Nội dung list value không đổi | **Không** |
| Cấu trúc nguồn bị sửa **đồng thời với** `copyOf` | Có snapshot nguyên tử, nhất quán | **Không được bảo đảm bởi `copyOf`** |
| So sánh danh tính kết quả với nguồn | Luôn là hai object khác nhau | **Không**; API có thể tái sử dụng một instance unmodifiable thích hợp |

Vì vậy, trong tài liệu thiết kế cần nêu rõ “snapshot của **cấu trúc collection**” hoặc “snapshot của **toàn bộ giá trị miền**” thay vì dùng từ *immutable* một cách mơ hồ.

## 3. Những kiểm thử bắt buộc để xác nhận độc lập

### 3.1. Test A — trạng thái ban đầu đúng

Lấy nguồn mutable đã biết, tạo snapshot và kiểm tra snapshot có giá trị kỳ vọng:

```java
var source = new java.util.ArrayList<>(
        java.util.List.of("X", "Y"));
var result = java.util.List.copyOf(source);

if (!result.equals(java.util.List.of("X", "Y"))) {
    throw new AssertionError("Wrong initial contents");
}
```

Test này **cần**, nhưng chưa chứng minh độc lập. Một view của nguồn cũng sẽ pass vì tại thời điểm này hai đối tượng đều hiển thị `[X,Y]`.

### 3.2. Test B — sửa nguồn sau khi tạo kết quả

```java
source.set(0, "NEW");
source.add("Z");

if (!result.equals(java.util.List.of("X", "Y"))) {
    throw new AssertionError("Result changed after source mutation");
}
```

Đây là phần trọng tâm: `result` phải giữ nguyên thành viên ở thời điểm copy. Nếu thay `List.copyOf(source)` bằng `Collections.unmodifiableList(source)`, test này **không pass** vì view phản ánh sửa đổi từ nguồn.

### 3.3. Test C — nguồn vẫn có thể thay đổi

Không nên vô tình khóa cả nguồn:

```java
if (!source.equals(java.util.List.of("NEW", "Y", "Z"))) {
    throw new AssertionError("Source did not change as expected");
}
```

Điều này chứng minh bước kích thích test **thực sự đã sửa nguồn**. Nếu code test không làm nguồn thay đổi, kết luận “kết quả vẫn độc lập” có thể là một **false positive**.

### 3.4. Test D — kết quả từ chối sửa trực tiếp

```java
try {
    result.add("NOT_ALLOWED");
    throw new AssertionError("Expected UnsupportedOperationException");
} catch (UnsupportedOperationException expected) {
    // Hợp đồng unmodifiable được tuân thủ.
}
```

Đoạn trên cố ý bắt loại exception, **không phụ thuộc message** hoặc stack trace của JDK. Nhưng như đã nói, test D **không thay thế** test B.

### 3.5. Test E — sửa nguồn bằng những cách khác nhau

Khi nguồn là `List`, nên thử ít nhất:
- `add`: thêm thành viên.
- `remove`: xóa thành viên.
- `set`: thay phần tử tại vị trí.

Với `Set`, thử `add` và `remove`; với `Map`, thử `put` trên khóa có sẵn, `put` khóa mới và `remove`. Việc thử nhiều loại mutation giúp phát hiện wrapper, alias hoặc copy không đúng hợp đồng.

Không nhất thiết viết hàng trăm test trùng lặp. Hãy chọn mỗi nhóm mutation có rủi ro lớn với API đang xây và một test contract tổng hợp cho snapshot.

## 4. Ma trận kiểm thử cho List, Set, Map và Collector

| Đầu vào mutable | API tạo kết quả | Kích thích sau khi tạo | Điều kiện pass về độc lập | Kiểm tra khác |
| --- | --- | --- | --- | --- |
| `ArrayList<String>` | `List.copyOf(source)` | `set/add/remove` nguồn | `List` kết quả giữ thứ tự và các phần tử cũ | `result.add` bị từ chối |
| `LinkedHashSet<String>` | `Set.copyOf(source)` | `add/remove` nguồn | Thành viên tập kết quả không đổi theo `equals/contains` | Không assert thứ tự duyệt |
| `HashMap<String,Integer>` | `Map.copyOf(source)` | `put/remove` nguồn | `get(key)`, `size`, `containsKey` phản ánh bản cũ | `result.put` bị từ chối |
| `ArrayList<String>` | `Collections.unmodifiableList(source)` | `source.add` | **Kỳ vọng view thay đổi**; đây là test phân biệt | `view.add` vẫn bị từ chối |
| `HashMap<String,Integer>` | `Collections.unmodifiableMap(source)` | `source.put` | **Kỳ vọng view phản ánh giá trị mới** | `view.put` bị từ chối |
| `ArrayList<String>` | `source.stream().collect(toUnmodifiableList())` | `source.set` sau terminal operation | Collection kết quả không phản ánh thay đổi thành viên nguồn | Không cho sửa |
| `List<List<String>>` hoặc `Map<K,List<V>>` | `copyOf` chỉ ở lớp ngoài | Sửa collection con qua tham chiếu cũ | **Thay đổi con vẫn có thể nhìn thấy** | Test cho thấy nhu cầu defensive copy sâu hơn |
| Dữ liệu chứa `null` | `List/Set/Map.copyOf` | Thực hiện copy | `NullPointerException` theo hợp đồng | Trường hợp không hợp lệ, khác mục đích test độc lập |
| List có giá trị lặp | `Set.copyOf` | Tạo tập | `size` bằng số giá trị phân biệt | Không mặc định giữ phần tử đầu tiên |

Lưu ý quan trọng cho `Set.copyOf`: khi các phần tử của nguồn bằng nhau theo `equals`, kết quả chỉ giữ một đại diện cho mỗi nhóm. Việc chọn đại diện nào và thứ tự duyệt Set không phải là cơ sở test ổn định. Với `Map.copyOf`, map nguồn đã có một entry cho mỗi key nên phải kiểm thử **duplicate keys** ở giai đoạn xây builder, không phải tại thao tác copy.

## 5. Chương trình hoàn chỉnh chạy 19 phép kiểm thử, không phụ thuộc thư viện ngoài

### 5.1. Môi trường

Sử dụng một **JDK đang được bảo trì và cập nhật bản vá**, chẳng hạn JDK 21 hoặc 25 LTS theo chính sách dự án. Ví dụ dùng Java 10 APIs `List.copyOf`/`Set.copyOf`/`Map.copyOf`/`Collectors.toUnmodifiableList` và cú pháp tương thích Java hiện đại. Không phải cài Java 10 lỗi thời.

```bash
java -version
javac -version
```

Tạo đúng tệp **`SnapshotIsolationLab.java`** với mã nguồn sau:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.HashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

public class SnapshotIsolationLab {
    private static int tests;

    // Không phụ thuộc assert của JVM: mặc định Java có thể tắt -ea.
    private static void check(String name, boolean condition) {
        if (!condition) {
            throw new AssertionError("FAILED " + name);
        }
        tests++;
        System.out.println("PASS " + name);
    }

    // Kiểm tra chính xác loại ngoại lệ theo hợp đồng.
    private static void expect(String name,
            Class<? extends RuntimeException> expected,
            Runnable action) {
        try {
            action.run();
        } catch (RuntimeException ex) {
            if (!expected.isInstance(ex)) {
                throw new AssertionError(
                        name + ": unexpected exception", ex);
            }
            check(name, true);
            return;
        }
        throw new AssertionError(
                name + ": expected " + expected.getSimpleName());
    }

    // Class mô hình hóa API nhận dữ liệu mutable từ caller.
    private static final class Catalog {
        private final List<String> codes;
        private final Set<String> roles;
        private final Map<String, Integer> limits;

        Catalog(Collection<String> codes,
                Collection<String> roles,
                Map<String, Integer> limits) {
            this.codes = List.copyOf(codes);
            this.roles = Set.copyOf(roles);
            this.limits = Map.copyOf(limits);
        }

        List<String> codes() { return codes; }
        Set<String> roles() { return roles; }
        Map<String, Integer> limits() { return limits; }
    }

    public static void main(String[] args) {
        // A. List.copyOf vs unmodifiable live view.
        var codesSource = new ArrayList<>(List.of("A", "B"));
        var codesSnapshot = List.copyOf(codesSource);
        var codesView = Collections.unmodifiableList(codesSource);

        codesSource.set(0, "X");
        codesSource.add("C");

        check("list-snapshot-isolated",
                codesSnapshot.equals(List.of("A", "B")));
        check("list-view-tracks-source",
                codesView.equals(List.of("X", "B", "C")));
        expect("snapshot-rejects-add",
                UnsupportedOperationException.class,
                () -> codesSnapshot.add("D"));
        expect("view-rejects-add",
                UnsupportedOperationException.class,
                () -> codesView.add("D"));

        // B. Set.copyOf: thành viên cũ không đổi, không test thứ tự.
        var rolesSource = new LinkedHashSet<>(
                List.of("read", "write"));
        var rolesSnapshot = Set.copyOf(rolesSource);
        rolesSource.add("admin");
        check("set-snapshot-isolated",
                rolesSnapshot.equals(Set.of("read", "write")));

        // C. Map.copyOf vs unmodifiable live view.
        var limitsSource = new HashMap<String, Integer>();
        limitsSource.put("max", 3);
        var limitsSnapshot = Map.copyOf(limitsSource);
        var limitsView = Collections.unmodifiableMap(limitsSource);

        limitsSource.put("max", 5);
        limitsSource.put("extra", 2);

        check("map-snapshot-isolated",
                limitsSnapshot.equals(Map.of("max", 3)));
        check("map-view-tracks-source",
                limitsView.equals(Map.of("max", 5, "extra", 2)));

        // D. Defensive copy khi nhận dữ liệu; getter giữ contract.
        var catalog = new Catalog(
                codesSource, rolesSource, limitsSource);
        codesSource.add("Z");
        rolesSource.remove("read");
        limitsSource.put("max", 8);

        check("catalog-list-defensive",
                catalog.codes().equals(List.of("X", "B", "C")));
        check("catalog-set-defensive",
                catalog.roles().contains("read")
                        && catalog.roles().size() == 3);
        check("catalog-map-defensive",
                catalog.limits().get("max") == 5);
        expect("catalog-getter-unmodifiable",
                UnsupportedOperationException.class,
                () -> catalog.codes().add("D"));

        // E. Tính bất biến nông: cùng object phần tử bị sửa.
        var builder = new StringBuilder("v1");
        var builders = new ArrayList<StringBuilder>();
        builders.add(builder);
        var shallow = List.copyOf(builders);

        builder.append("-v2");
        check("shallow-element-shared",
                shallow.get(0).toString().equals("v1-v2"));

        // F. Map.copyOf không copy sâu List value.
        var nested = new HashMap<String, List<String>>();
        var tags = new ArrayList<>(List.of("t1"));
        nested.put("tags", tags);

        var shallowOuter = Map.copyOf(nested);
        var stableInner = Map.copyOf(
                Map.of("tags", List.copyOf(tags)));

        tags.add("t2");
        check("nested-value-still-mutable",
                shallowOuter.get("tags")
                        .equals(List.of("t1", "t2")));
        check("nested-defensive-copy",
                stableInner.get("tags").equals(List.of("t1")));

        // G. Input không hợp lệ: null bị copyOf từ chối.
        var badList = new ArrayList<String>();
        badList.add(null);
        expect("null-list-copy-rejected",
                NullPointerException.class,
                () -> List.copyOf(badList));

        var badMap = new HashMap<String, String>();
        badMap.put("x", null);
        expect("null-map-copy-rejected",
                NullPointerException.class,
                () -> Map.copyOf(badMap));

        // H. Set.copyOf gom phần tử bằng nhau.
        check("set-copy-deduplicates",
                Set.copyOf(List.of("a", "a", "b")).size() == 2);

        // I. Terminal Stream.collect tạo kết quả riêng.
        var eventSource = new ArrayList<>(
                List.of("red", "blue"));
        var streamResult = eventSource.stream()
                .collect(Collectors.toUnmodifiableList());

        eventSource.set(0, "green");
        check("collector-independent",
                streamResult.equals(List.of("red", "blue")));
        expect("collector-unmodifiable",
                UnsupportedOperationException.class,
                () -> streamResult.add("pink"));

        System.out.println("ALL TESTS PASSED: " + tests);
    }
}
```

### 5.2. Biên dịch và chạy

Trong thư mục chứa tệp, chạy:

```bash
javac SnapshotIsolationLab.java
java SnapshotIsolationLab
```

Hàm `check` ném `AssertionError` ngay khi điều kiện sai. Hàm `expect` kiểm tra **đúng loại ngoại lệ** và cũng ném `AssertionError` nếu không thấy ngoại lệ. Vì không dùng keyword `assert` của Java, bạn **không cần bật `-ea`** để nhận biết test fail. Chương trình kết thúc bất thường khi một phép thử không đạt.

### 5.3. Stdout chuẩn — 19 test PASS

```text
PASS list-snapshot-isolated
PASS list-view-tracks-source
PASS snapshot-rejects-add
PASS view-rejects-add
PASS set-snapshot-isolated
PASS map-snapshot-isolated
PASS map-view-tracks-source
PASS catalog-list-defensive
PASS catalog-set-defensive
PASS catalog-map-defensive
PASS catalog-getter-unmodifiable
PASS shallow-element-shared
PASS nested-value-still-mutable
PASS nested-defensive-copy
PASS null-list-copy-rejected
PASS null-map-copy-rejected
PASS set-copy-deduplicates
PASS collector-independent
PASS collector-unmodifiable
ALL TESTS PASSED: 19
```

Các phép kiểm tra đã được thử trên một JDK hiện đại. Output **không in thứ tự duyệt `HashMap` hoặc `Set.copyOf`**, không phụ thuộc danh tính object, và không so sánh message của ngoại lệ, nên là kiểm thử theo **hợp đồng API**, không theo chi tiết triển khai.

## 6. Phân tích từng nhóm kiểm thử trong lab

### 6.1. Nhóm List — chứng minh hai thuộc tính tách biệt

`codesSnapshot` và `codesView` đều được tạo khi `codesSource` là `[A,B]`. Sau `codesSource.set(0,"X")` và `add("C")`:

- `codesSnapshot` vẫn là `[A,B]`.
- `codesView` hiện là `[X,B,C]` vì nó là một view của nguồn.
- Cả hai cùng từ chối `add("D")`.

Điểm quyết định là kiểm tra **nội dung sau khi nguồn bị sửa**. Nếu một test chỉ xác nhận cả hai đều ném `UnsupportedOperationException` thì nó không phân biệt được snapshot với view.

### 6.2. Nhóm Set — kiểm tra bằng tập thành viên, không thứ tự

`rolesSource` là `LinkedHashSet` ban đầu chứa `read` và `write`, rồi có thêm `admin` sau `Set.copyOf`. `rolesSnapshot.equals(Set.of("read","write"))` trả `true`.

Tại đây test **không yêu cầu** `iterator().next()` trả `read` hay `write` trước, vì thứ tự duyệt `Set.copyOf` không được bảo đảm. Một test kiểu `assertEquals("[read, write]", snapshot.toString())` là rủi ro, dù logic snapshot đúng.

### 6.3. Nhóm Map — so sánh map theo entry và key

`limitsSnapshot` chụp `max=3`. Sau khi nguồn được sửa thành `max=5` và thêm `extra=2`:

- `limitsSnapshot.equals(Map.of("max",3))` vẫn đúng.
- `limitsView.equals(Map.of("max",5,"extra",2))` đúng vì view đọc xuyên qua backing map.

`Map.equals` so sánh tập các ánh xạ key/value, không yêu cầu một thứ tự duyệt cụ thể. Do đó đây là cách kiểm tra chính xác và dễ bảo trì hơn việc so sánh `Map.toString()`.

### 6.4. Nhóm Catalog — kiểm thử defensive copying tại constructor

`new Catalog(codesSource,rolesSource,limitsSource)` tạo snapshot ngay trong constructor. Sau đó mã test sửa **cả ba nguồn** từ bên ngoài. Nếu `Catalog` đã lưu thẳng tham chiếu nguồn mutable, các điều kiện `catalog-*-defensive` sẽ thất bại.

Getter `codes()` trả list không cho sửa; kết quả `expect("catalog-getter-unmodifiable",...)` xác nhận caller không thể thêm một mã qua đường getter.

Đây là mẫu kiểm thử rất hữu ích cho class chứa cấu hình, giá trị trả từ repository hoặc danh sách quyền mà caller không được can thiệp.

### 6.5. Nhóm shallow-element — chỉ ra giới hạn thực tế

Một `StringBuilder` có thể được sửa trong khi vẫn giữ cùng identity. `List.copyOf` không thay thế nó bằng `String` hoặc một bản sao `StringBuilder`. Test `shallow-element-shared` **cố ý xác nhận rằng thay đổi của phần tử vẫn nhìn thấy được**, để ngăn tuyên bố sai rằng `copyOf` tạo deep immutable data.

### 6.6. Nhóm nested map — phải copy cả giá trị con nếu muốn cố định

Hai map đều có kiểu tĩnh `Map<String,List<String>>`:

- `shallowOuter = Map.copyOf(nested)`: phần value `List<String>` vẫn là `tags` mutable.
- `stableInner = Map.copyOf(Map.of("tags", List.copyOf(tags)))`: value đã được chuyển thành list snapshot trước khi copy map ngoài.

Sau `tags.add("t2")`, map thứ nhất nhìn thấy danh sách `[t1,t2]`; map thứ hai vẫn có `[t1]`. Với các phần tử `String` bất biến, đây là mức copy đủ để ổn định giá trị chuỗi của ví dụ. Nếu value list chứa bean mutable, phải copy chính bean hoặc chuyển thành value object bất biến.

### 6.7. Null, duplicate và collector là các hợp đồng liên quan

`List.copyOf` từ chối phần tử null; `Map.copyOf` từ chối key hoặc value null; `Set.copyOf` cũng từ chối null. Đây là các ca kiểm thử input validation **khác** với việc kiểm tra độc lập, nhưng cần đưa vào suite để API không âm thầm thay dữ liệu.

`Set.copyOf(List.of("a","a","b"))` có hai thành viên phân biệt, không ném lỗi duplicate. Đừng dùng kích thước đầu vào `3` làm kỳ vọng cho kích thước snapshot Set.

`Collectors.toUnmodifiableList()` tạo list không cho sửa sau khi Stream kết thúc. Sửa cấu trúc nguồn về sau không làm thay đổi list kết quả đã collect. Tuy nhiên, nếu Stream truyền tiếp **phần tử mutable**, bản chất chia sẻ tham chiếu như `copyOf` vẫn cần được đánh giá.

## 7. Kiểm thử hồi quy để phân biệt đúng và sai trong implementation

### 7.1. Một implementation dễ gây lỗi

Đoạn sau minh họa việc một lớp giữ **view trên nguồn mutable của caller**, thay vì snapshot:

```java
import java.util.Collections;
import java.util.List;

final class BuggyCatalog {
    private final List<String> codes;

    BuggyCatalog(List<String> supplied) {
        this.codes = Collections.unmodifiableList(supplied);
    }

    List<String> codes() {
        return codes;
    }
}
```

Nếu bên gọi còn giữ `supplied`, họ có thể gọi `supplied.add("INJECTED")`. Getter của `BuggyCatalog` sẽ phản ánh phần tử ấy, dù getter không cho sửa trực tiếp.

### 7.2. Phiên bản sửa đúng hợp đồng snapshot

```java
import java.util.List;

final class SafeCatalog {
    private final List<String> codes;

    SafeCatalog(List<String> supplied) {
        this.codes = List.copyOf(supplied);
    }

    List<String> codes() {
        return codes;
    }
}
```

Hai lớp này là **mã minh họa tách biệt khỏi chương trình lab** và chỉ nên dùng trong các tệp Java có tên/đường dẫn phù hợp dự án. Kiểm thử hồi quy có thể cùng một kịch bản:

```java
// Trong một phương thức:
var mutable = new java.util.ArrayList<>(
        java.util.List.of("A"));

var unsafe = new BuggyCatalog(mutable);
var safe = new SafeCatalog(mutable);

mutable.add("B");

// unsafe.codes().size() == 2
// safe.codes().size() == 1
```

Chỉ cần một mutation nguồn sau constructor đã bộc lộ khác biệt. Nếu nghiệp vụ **thật sự mong muốn live view**, `BuggyCatalog` không nhất thiết sai; vấn đề là hợp đồng phải nói rõ kết quả theo dõi nguồn. Trong ví dụ này, mục tiêu đã xác định là snapshot nên view là sai lựa chọn.

### 7.3. Mutation testing đối với chính test suite

Một cách tự kiểm tra chất lượng test là **cố tình thay `List.copyOf` bằng `Collections.unmodifiableList`** trong một bản sao mã thử nghiệm. Test về `add` sẽ vẫn pass, nhưng test về `source.add`/`source.set` sau khi tạo snapshot phải thất bại. Nếu mọi test đều xanh, suite chưa kiểm chứng được sự độc lập như mong đợi.

Đừng thực hiện mutation testing trực tiếp trên nhánh chính hoặc dữ liệu production. Thử trên fixture/test branch có thể phục hồi, chỉ để biết test có thực sự phát hiện lỗi mong muốn hay không.

## 8. Viết cùng ý tưởng bằng JUnit trong dự án

Chương trình ở phần 5 chạy độc lập với JDK. Khi dự án **đã có JUnit Jupiter** được cấu hình, có thể diễn đạt cùng hợp đồng bằng `assertEquals` và `assertThrows`:

```java
import static org.junit.jupiter.api.Assertions.*;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import org.junit.jupiter.api.Test;

class SnapshotContractTest {
    @Test
    void copyOfIsIndependentFromMutableSource() {
        var source = new ArrayList<>(
                List.of("A", "B"));
        var snapshot = List.copyOf(source);

        source.set(0, "X");
        source.add("C");

        assertEquals(List.of("A", "B"), snapshot);
        assertEquals(List.of("X", "B", "C"), source);
        assertThrows(UnsupportedOperationException.class,
                () -> snapshot.add("D"));
    }

    @Test
    void unmodifiableViewStillTracksSource() {
        var source = new ArrayList<>(List.of("A"));
        var view = Collections.unmodifiableList(source);

        source.add("B");

        assertEquals(List.of("A", "B"), view);
        assertThrows(UnsupportedOperationException.class,
                () -> view.add("C"));
    }
}
```

Đây là **JUnit test class** phụ thuộc vào JUnit Jupiter do hệ thống build của dự án cung cấp; không chạy bằng `javac SnapshotContractTest.java` trên một JDK trống nếu chưa cấu hình dependency và test runner. Không nhầm test framework này với ví dụ độc lập ở phần 5.

### Nguyên tắc sử dụng assertion

- Dùng `assertEquals` cho List có thứ tự; dùng `assertEquals` trên Set/Map hoặc kiểm tra `contains/size/get` cho kiểu không có thứ tự duyệt.
- Dùng `assertThrows(UnsupportedOperationException.class, ...)` khi muốn xác nhận thao tác sửa bị chặn; vẫn phải có test nguồn thay đổi sau copy.
- Dùng `assertNotEquals` nếu có lý do cụ thể; tránh viết assertion chỉ kiểm tra cả nguồn và kết quả không `null`.
- **Không dùng `assertNotSame(source,snapshot)` làm bằng chứng độc lập.** `copyOf` được phép tái sử dụng instance phù hợp khi nguồn đã unmodifiable; danh tính object không phải hợp đồng của collection dạng value-based.
- Không kiểm tra chính xác chuỗi exception message; thông báo có thể khác giữa các bản JDK dù loại exception đúng.

## 9. Các trường hợp cần tránh kết luận sai

### 9.1. Source chưa bị sửa: false positive

Kiểm tra `copy.equals(source)` ngay sau khi tạo không chứng minh kết quả độc lập. Mọi view đều có thể bằng nguồn ở thời điểm đầu.

**Cần test có hành động cụ thể:** thêm, xóa, thay phần tử/entry ở nguồn **sau khi** copy và đối chiếu snapshot với giá trị ban đầu.

### 9.2. Source không còn được giữ: thiếu bằng chứng

Nếu một factory tạo `List.copyOf` từ một List local rồi hủy tham chiếu nguồn, có thể khó mô phỏng việc caller còn giữ alias. Trong unit test, chủ động tạo source mutable ở phía caller và truyền vào constructor, sau đó giữ reference để sửa. Đây là cách tái hiện rủi ro aliasing.

### 9.3. So sánh hai đối tượng bằng identity

Javadoc của các factory `List.of/copyOf`, `Set.of/copyOf` và `Map.of/copyOf` có các lưu ý về value-based instances và khả năng tái sử dụng. Việc `source == result` hay `source != result` **không phải** cách đúng để tuyên bố tính độc lập. Hãy so **trạng thái và hành vi** sau khi sửa nguồn.

### 9.4. Assert thứ tự không được bảo đảm

`Set.copyOf` và `Map.copyOf` không bảo đảm thứ tự duyệt. Test `result.toString().equals(...)` hoặc `result.iterator().next()` có thể fail ở JDK khác dù mọi thành viên đúng.

Thay bằng:
- `set.equals(Set.of("A","B"))` hoặc `set.size()==2 && set.contains("A")`.
- `map.equals(Map.of("A",1,"B",2))` hoặc `map.get("A")==1` và `containsKey("B")`.
- Chỉ test thứ tự khi hợp đồng **thực sự bảo đảm** thứ tự, chẳng hạn `List` hoặc một cấu trúc có contract sắp xếp riêng.

### 9.5. Nhầm giữa snapshot và deep copy

Nếu value/element mutable, test chỉ sửa list/map **bên ngoài** có thể xanh nhưng trạng thái bên trong vẫn thay đổi. Một suite cần test cả một trong các tình huống lồng nhau có giá trị nghiệp vụ: `List<MutableItem>`, `Map<String,List<String>>` hoặc `Map<Id,MutableRecord>`.

Đối với keys của Map hoặc members của Set, nếu `equals/hashCode` phụ thuộc trường mutable bị sửa, việc sửa sau khi đưa đối tượng vào collection có thể làm phép tra cứu hoạt động bất nhất. Tránh dùng các loại key như vậy; sử dụng value objects có equality ổn định hoặc chuyển đổi sang khóa bất biến.

### 9.6. Null và trùng làm test fail vì lý do khác

`List/Set/Map.copyOf` từ chối null. Với đầu vào chứa null, exception xuất hiện **trước khi** bạn kiểm chứng được ảnh hưởng của việc sửa nguồn. Hãy tách testcase **input validation** khỏi testcase **snapshot independence**.

`Set.copyOf` tự loại trùng. Kết quả `size` có thể nhỏ hơn size nguồn **ngay trước** khi có mutation. Đừng quy kết chênh lệch ban đầu là lỗi snapshot; phải tính theo ngữ nghĩa Set.

### 9.7. Tính đồng thời: đừng tạo race test không ổn định

Nếu collection nguồn bị sửa **trong lúc** `copyOf` đang duyệt, `copyOf` không tự cung cấp transaction hoặc khóa để đảm bảo một ảnh chụp nguyên tử. Một test đa luồng chạy “ngẫu nhiên” có thể xanh hoặc đỏ tùy lịch trình.

Để kiểm thử độc lập của snapshot theo hợp đồng, **dựng nguồn ở trạng thái ổn định, copy xong rồi mới sửa nguồn**. Với concurrency, hãy thiết kế và kiểm thử riêng cơ chế đồng bộ/công bố, ví dụ writer xây bản sao private → publish qua `AtomicReference` hoặc `volatile` theo mô hình phù hợp. Không coi `List.copyOf` là công cụ thay cho thread synchronization.

## 10. Kiểm thử sự độc lập trong API nhiều phiên bản dữ liệu

Một hệ thống có thể cập nhật cấu hình nhiều lần. Kiểm tra cả hai snapshot:

```java
// Trong một phương thức:
var working = new java.util.HashMap<String, Integer>();
working.put("timeoutMs", 500);

var v1 = java.util.Map.copyOf(working);
working.put("timeoutMs", 1000);
var v2 = java.util.Map.copyOf(working);

if (v1.get("timeoutMs") != 500) {
    throw new AssertionError("v1 changed");
}
if (v2.get("timeoutMs") != 1000) {
    throw new AssertionError("v2 wrong");
}
```

Điều này kiểm tra rằng `v1` vẫn chứa giá trị ban đầu và `v2` phản ánh trạng thái ở lúc tạo. Bản thân `Map.copyOf` không lưu lịch sử hoặc tự gắn số phiên bản; việc đặt tên `v1/v2` và quản lý lifecycle thuộc ứng dụng.

Khi giữ snapshot trong một service, test tốt còn xác nhận rằng:
1. Bản mới chỉ được công bố **sau khi validate toàn bộ**.
2. Một request lấy một tham chiếu snapshot ở đầu tác vụ và dùng nó nhất quán, không đọc từng key qua nhiều lần fetch có thể gặp nhiều phiên bản.
3. Nếu việc nạp cấu hình mới lỗi, snapshot đang hoạt động không bị thay bằng một map nửa chừng.

Những điểm trên là yêu cầu hệ thống **xây quanh** `Map.copyOf`, không phải bảo đảm tự động từ phương thức copy.

## 11. Bài tập thực hành có lời giải

### Bài 1 — Chứng minh độc lập của List

```java
var source = new java.util.ArrayList<>(java.util.List.of("A"));
var result = java.util.List.copyOf(source);
source.add("B");
```

**Hỏi:** `result` còn chứa gì? Cần assertion nào?

**Đáp án:** `result.equals(List.of("A"))` phải đúng. Nên thêm assertion `source.equals(List.of("A","B"))` để xác nhận mutation nguồn đã thực hiện. Chỉ kiểm tra `result.size()==1` cũng có ích nhưng so sánh toàn bộ giá trị dễ phát hiện thêm lỗi khác.

### Bài 2 — Test không đủ mạnh

Một unit test chỉ viết:

```java
var view = java.util.Collections.unmodifiableList(source);
assertThrows(UnsupportedOperationException.class,
        () -> view.add("C"));
```

**Hỏi:** Có chứng minh view độc lập với nguồn không?

**Đáp án:** Không. Test chỉ cho thấy view không hỗ trợ sửa qua reference được trả. Cần sửa `source` **sau khi** tạo kết quả và kiểm tra snapshot giữ nội dung cũ; với `unmodifiableList`, view sẽ nhìn thấy thay đổi đó.

### Bài 3 — Dùng đúng Set assertions

```java
var source = new java.util.LinkedHashSet<>(
        java.util.List.of("A", "B"));
var snapshot = java.util.Set.copyOf(source);
source.add("C");
```

**Đáp án:** `snapshot.equals(Set.of("A","B"))` đúng; `snapshot.contains("C")` sai. Không yêu cầu `snapshot.toString()` có thứ tự `[A,B]`. Nếu `source` có phần tử trùng từ trước, phải chú ý Set đã chỉ giữ giá trị phân biệt.

### Bài 4 — Map entry bị thay

```java
var source = new java.util.HashMap<String, Integer>();
source.put("limit", 5);
var snapshot = java.util.Map.copyOf(source);
source.put("limit", 9);
```

**Đáp án:** `snapshot.get("limit")==5`, trong khi `source.get("limit")==9`. Có thể kiểm tra cả `snapshot.size()==1`. Không phụ thuộc vào thứ tự in Map.

### Bài 5 — Test defensive copying ở constructor

Một service nhận `List<String> ids` từ caller và lưu lại. Nên kiểm thử như thế nào?

**Đáp án:** Truyền một `ArrayList` mutable, tạo service, sửa `ArrayList` ở phía caller, đọc lại getter. Nếu hợp đồng yêu cầu snapshot, getter phải giữ các ID trước khi sửa. Thêm test gọi `getter.add(...)` và mong đợi `UnsupportedOperationException`; hai test xác nhận hai thuộc tính khác nhau.

### Bài 6 — Lỗi deep-copy assumption

```java
var item = new StringBuilder("old");
var snapshot = java.util.List.copyOf(
        java.util.List.of(item));
item.append("-new");
```

**Đáp án:** `snapshot.get(0).toString()` là `"old-new"`. `copyOf` giữ tham chiếu phần tử. Để snapshot nội dung chuỗi, chuyển item thành `String` trước: `List.copyOf(List.of(item.toString()))`.

### Bài 7 — Map chứa List mutable

```java
var tags = new java.util.ArrayList<>(
        java.util.List.of("A"));
var source = java.util.Map.of("tags", tags);
var copy = java.util.Map.copyOf(source);
tags.add("B");
```

**Đáp án:** `copy.get("tags")` nhìn thấy `[A,B]` vì value `tags` vẫn là một List mutable được chia sẻ. Để tạo snapshot cho collection lồng, hãy copy `List.copyOf(tags)` **trước khi** thêm `B`, rồi công bố map ngoài. Kết quả cần các phần tử trong list cũng là giá trị bất biến nếu yêu cầu bất biến sâu.

### Bài 8 — Copy kết quả đã unmodifiable

Tại sao không nên kiểm tra:

```java
var original = java.util.List.of("A", "B");
var copied = java.util.List.copyOf(original);
if (copied == original) {
    throw new AssertionError("Copy did not allocate!");
}
```

**Đáp án:** Không có yêu cầu `copyOf` luôn cấp phát instance mới; nó có thể tái sử dụng unmodifiable list phù hợp. Hợp đồng là không cho sửa và không phản ánh thay đổi cấu trúc nguồn, **không phải** identity khác nhau. Test trên còn dùng `==` làm tiêu chuẩn không đúng.

### Bài 9 — Race condition

Một thread thực hiện `Map.copyOf(sharedHashMap)` cùng lúc thread khác liên tục `put`. Có thể kết luận snapshot nguyên tử vì test thường xuyên xanh không?

**Đáp án:** Không. `HashMap` không được thiết kế cho truy cập sửa đồng thời không đồng bộ và `copyOf` không khóa nguồn. Cần kiểm soát cách xây/sao chép và công bố dữ liệu bằng synchronization/ownership phù hợp. Với unit test snapshot, hãy copy trên nguồn ổn định trước.

### Bài 10 — Thiết kế regression test cho thư viện

Một thay đổi refactor thay constructor `List.copyOf(input)` bằng `Collections.unmodifiableList(input)`. Test nào nhất thiết phải bắt được lỗi?

**Đáp án:** Test **mutate source after construction** rồi khẳng định getter vẫn có trạng thái lúc tạo. Chỉ test getter không cho sửa sẽ không bắt được thay đổi, vì cả hai implementation đều từ chối `add`.

## 12. Checklist kiểm thử trong code review

- [ ] Xác nhận kết quả là snapshot hay live view theo **hợp đồng API**; không suy luận chỉ từ từ “read-only”.
- [ ] Tạo dữ liệu nguồn **mutable và có ít nhất hai phần tử/entry phân biệt** ở thời điểm chuẩn bị.
- [ ] Tạo kết quả trước, sau đó **thực sự** gọi `add/set/remove/put` trên nguồn.
- [ ] So sánh giá trị kết quả với **trạng thái đã biết ở thời điểm snapshot**.
- [ ] Kiểm tra nguồn đã thay đổi đúng, tránh test giả xanh.
- [ ] Test thao tác sửa kết quả ném `UnsupportedOperationException`, riêng biệt với test độc lập.
- [ ] Với `Set/Map`, so sánh thành viên/entries thay vì chuỗi hiển thị hoặc iteration order.
- [ ] Không dùng `==`/`assertNotSame` làm bằng chứng `copyOf` cấp phát object mới.
- [ ] Kiểm tra defensive copy trong constructor và getter ở ranh giới module.
- [ ] Kiểm tra ít nhất một trường hợp giá trị/element mutable để tránh ngộ nhận deep copy.
- [ ] Kiểm tra collection lồng nhau nếu domain chứa `List`/`Map` bên trong.
- [ ] Kiểm thử null và duplicate như **ca input validation riêng**, không trộn với mục tiêu độc lập.
- [ ] Không suy đoán tính nhất quán khi nguồn bị sửa đồng thời trong lúc copy.
- [ ] Chương trình `SnapshotIsolationLab.java` biên dịch, chạy, in **19 dòng PASS** và dòng tổng kết đúng.
- [ ] Các test xác nhận **hợp đồng công khai**, không khóa chặt implementation JDK hoặc ngoại lệ message.

## 13. Kết luận

**Để chứng minh kết quả độc lập khỏi nguồn, bắt buộc phải sửa nguồn *sau khi tạo kết quả* và kiểm tra kết quả vẫn giữ trạng thái ban đầu.** Test chỉ xác nhận collection không cho `add/put` chưa đủ, vì **unmodifiable live view** cũng chặn thao tác sửa qua view nhưng phản ánh thay đổi từ backing collection.

`List.copyOf`, `Set.copyOf` và `Map.copyOf` (Java 10) là công cụ tốt để công bố snapshot **cấu trúc collection**. Muốn bảo vệ toàn bộ trạng thái nghiệp vụ, hãy đảm bảo phần tử/key/value đủ bất biến, tạo defensive copy ở các tầng lồng nhau và áp dụng chính sách an toàn đồng thời khi dữ liệu chia sẻ giữa nhiều thread. Các quy tắc kiểm thử này vẫn hữu ích với Java hiện đại.

## Tài liệu tham khảo chính thức

- [Oracle Java SE 25 API — List.copyOf](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): snapshot theo thứ tự nguồn, từ chối null, không hỗ trợ sửa.
- [Oracle Java SE 25 API — Set.copyOf](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Set.html#copyOf(java.util.Collection)): snapshot tập thành viên, gộp trùng, không cam kết thứ tự duyệt.
- [Oracle Java SE 25 API — Map.copyOf](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html#copyOf(java.util.Map)): snapshot entry, từ chối null key/value, không cam kết iteration order.
- [Oracle Java SE 25 API — Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)): view không cho sửa và đọc xuyên qua backing list.
- [Oracle Java SE 25 API — Collection: View Collections](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collection.html): phân biệt unmodifiable view và collection có trạng thái được quản lý riêng.
- [Oracle Java SE 25 API — Collectors.toUnmodifiableList](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html#toUnmodifiableList()): collector Java 10 tạo kết quả unmodifiable từ Stream.
- [Oracle — Creating Unmodifiable Lists, Sets, and Maps](https://docs.oracle.com/en/java/javase/25/core/creating-immutable-lists-sets-and-maps.html): hướng dẫn lựa chọn `copyOf` so với view.