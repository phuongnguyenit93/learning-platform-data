# So sánh collection, thứ tự, phần tử trùng và tập rỗng trong kiểm thử Spring Boot

## 1. Mục tiêu: assertion phải phản ánh đúng hợp đồng của collection

Ứng dụng Spring Boot thường trả về danh sách đơn hàng, tập quyền, kết quả tìm kiếm, bản đồ cấu hình hoặc các nhóm dữ liệu từ service/repository/API. Hai collection có cùng vài giá trị **chưa chắc có cùng ý nghĩa**: thứ tự có thể quan trọng, một phần tử có thể được phép lặp lại, và kết quả rỗng có thể khác hẳn `null`.

Khi kiểm thử, hãy quyết định rõ bốn điều trước khi viết assertion:

1. **Loại cấu trúc:** `List`, `Set`, `Map`, mảng hay một `Iterable` tùy biến?
2. **Thứ tự:** kết quả cần giữ đúng vị trí/phần tử hay được phép trả về theo bất kỳ thứ tự nào?
3. **Phần tử trùng:** số lần xuất hiện của mỗi phần tử có là một phần của hợp đồng không?
4. **Trống và null:** không có kết quả thì trả collection rỗng, `Optional.empty()`, hay `null` theo hợp đồng?

Một assertion quá lỏng có thể xanh dù hệ thống trả dư/thiếu dữ liệu. Một assertion quá chặt có thể đỏ khi thứ tự vốn không được bảo đảm thay đổi hợp lệ. Mục tiêu là kiểm tra **đúng thuộc tính cần bảo vệ**, không gò mọi collection vào một kiểu so sánh.

## 2. Hiểu cách Java so sánh List, Set, Map và Iterable

| Kiểu dữ liệu | `equals` có xét thứ tự? | Có biểu diễn phần tử trùng? | Ý nghĩa với assertion |
|---|---|---|---|
| `List` | **Có**: cùng kích thước, từng phần tử bằng nhau tại cùng vị trí | **Có** | `assertEquals(expectedList, actualList)` kiểm tra đủ cả thứ tự và số lần xuất hiện |
| `Set` | **Không**: cùng tập phần tử | **Không**: phần tử trùng bị gộp khi thêm | `assertEquals(expectedSet, actualSet)` phù hợp khi thứ tự và số lần lặp không thuộc hợp đồng |
| `Map` | **Không**: so sánh các cặp khóa–giá trị | Mỗi khóa duy nhất; giá trị có thể trùng | `assertEquals(expectedMap, actualMap)` kiểm tra ánh xạ, không kiểm tra thứ tự duyệt |
| `Iterable` bất kỳ | Không có quy tắc `equals` chung cho mọi implementation | Tùy implementation | Có thể dùng `assertIterableEquals` để so sánh **trình tự duyệt**, nhưng phải biết trình tự đó có được bảo đảm hay không |
| Mảng Java | `Object.equals` của mảng thường so sánh danh tính tham chiếu | Có | Dùng `assertArrayEquals` cho mảng; đừng nhầm với `List.equals` |

Ví dụ:

```java
List<String> a = List.of("A", "B", "A");
List<String> b = List.of("A", "A", "B");
boolean sameList = a.equals(b); // false: khác vị trí

Set<String> x = Set.of("A", "B");
Set<String> y = Set.of("B", "A");
boolean sameSet = x.equals(y);  // true: cùng phần tử
```

`List.equals`, `Set.equals` và `Map.equals` dựa vào `equals` của các phần tử/khóa/giá trị. Với DTO tùy biến chưa có quy tắc bình đẳng theo dữ liệu, `assertEquals(List<Dto>, List<Dto>)` có thể fail dù các trường hiển thị giống nhau. Với kiểu dữ liệu phù hợp, Java `record` tự cung cấp `equals` theo các component; với class thông thường, cân nhắc `equals/hashCode` hoặc assertion trích xuất các trường theo hợp đồng.

**Không lấy thứ tự duyệt của `HashSet` hoặc `HashMap` làm hợp đồng.** Chúng không bảo đảm thứ tự theo lúc thêm hay thứ tự sắp xếp. `LinkedHashSet` và `LinkedHashMap` có quy tắc thứ tự duyệt riêng, nhưng `equals` của `Set`/`Map` vẫn không tính thứ tự đó.

## 3. Chọn assertion theo thứ tự và số lần xuất hiện

| Hợp đồng thực tế | Cách kiểm tra phù hợp | Ví dụ |
|---|---|---|
| Thứ tự **quan trọng**, phần tử trùng **quan trọng** | JUnit `assertEquals(List, List)`, `assertIterableEquals`; AssertJ `containsExactly` | `["A", "B", "A"]` chỉ khớp đúng chuỗi đó |
| Thứ tự **không quan trọng**, phần tử trùng **quan trọng** | AssertJ `containsExactlyInAnyOrder` | `["A", "B", "A"]` khớp `["B", "A", "A"]`, nhưng không khớp `["A", "B"]` |
| Thứ tự **không quan trọng**, phần tử trùng **không có ý nghĩa** | `Set.equals`, hoặc kiểm tra tập phần tử | `{"A", "B"}` bằng `{"B", "A"}` |
| Thứ tự **quan trọng**, phần tử **phải duy nhất** | Assert thứ tự list **và** assert tính duy nhất | Danh sách quyền được sắp theo độ ưu tiên, không lặp quyền |
| Không có kết quả, trả về collection rỗng | `assertNotNull` + `assertTrue(isEmpty())`, AssertJ `isEmpty()` | `[]` là kết quả hợp lệ nhưng `null` là lỗi hợp đồng |

Các phép kiểm tra có vai trò khác nhau:

- `assertEquals(expected, actual)` với `List`: xác minh kích thước, vị trí, phần tử trùng dựa trên `List.equals`.
- `assertIterableEquals(expected, actual)` của JUnit Jupiter: so sánh theo thứ tự phần tử được lặp qua; hợp lý cho trình tự đã xác định, **không** phải công cụ bỏ qua thứ tự.
- `assertThat(actual).containsExactly(...)` của AssertJ: kiểm tra toàn bộ phần tử theo đúng thứ tự, không thừa/thiếu.
- `assertThat(actual).containsExactlyInAnyOrder(...)`: so sánh đầy đủ các phần tử, bỏ qua thứ tự **nhưng vẫn tính số lần lặp**.
- `assertThat(actual).containsOnly(...)`: xác minh các giá trị cho phép/hiện diện, **không dùng để xác nhận số lần lặp chính xác** vì phép kiểm tra này bỏ qua sự khác biệt về duplicate.
- `assertThat(actual).contains(...)`: kiểm tra các phần tử được nêu có mặt, không bảo đảm tập kết quả chỉ có những phần tử đó.

Một lỗi test rất phổ biến là dùng `actual.containsAll(expected)` để kết luận hai danh sách tương đương. Phép này chỉ hỏi từng giá trị trong `expected` có xuất hiện ở `actual` không; nó **không** kiểm tra thứ tự, số lần lặp hoặc phần tử thừa.

## 4. Ví dụ Java 17+ với JUnit Jupiter và AssertJ

Ví dụ sau có thể đặt vào một dự án Spring Boot dùng Java 17+ và dependency kiểm thử `spring-boot-starter-test` (cung cấp JUnit Jupiter/AssertJ trong cấu hình starter test thông dụng). Đây là test thuần Java, không cần tạo Spring context.

Tệp: `src/test/java/com/example/testing/CollectionAssertionsTest.java`

```java
package com.example.testing;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertIterableEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CollectionAssertionsTest {

    @Test
    void listComparisonChecksOrderAndDuplicates() {
        List<String> actual = List.of("A", "B", "A");
        List<String> expected = List.of("A", "B", "A");

        assertEquals(expected, actual);
        assertIterableEquals(expected, actual);
        assertThat(actual).containsExactly("A", "B", "A");

        assertNotEquals(expected, List.of("A", "A", "B"));
        assertNotEquals(expected, List.of("A", "B"));
    }

    @Test
    void compareWithoutOrderButKeepDuplicateCounts() {
        List<String> actual = List.of("B", "A", "A");

        assertThat(actual).containsExactlyInAnyOrder("A", "A", "B");
        assertThat(actual).containsOnly("A", "B");
        // containsOnly không xác minh A xuất hiện đúng hai lần.
    }

    @Test
    void setEqualityIgnoresIterationOrderAndRemovesDuplicates() {
        Set<String> actual =
                new LinkedHashSet<>(List.of("B", "A", "B"));

        assertEquals(Set.of("A", "B"), actual);
        assertEquals(2, actual.size());
        assertTrue(actual.contains("A"));
        assertFalse(actual.contains("C"));
    }

    @Test
    void emptyAndNullHaveDifferentMeanings() {
        List<String> actual = new ArrayList<>();

        assertNotNull(actual);
        assertTrue(actual.isEmpty());
        assertThat(actual).isEmpty();
        assertEquals(List.of(), actual);
    }

    @Test
    void mapEqualityChecksKeysAndValuesNotInsertionOrder() {
        Map<String, Integer> actual = new LinkedHashMap<>();
        actual.put("second", 2);
        actual.put("first", 1);

        Map<String, Integer> expected =
                Map.of("first", 1, "second", 2);

        assertEquals(expected, actual);
        assertThat(actual)
                .hasSize(2)
                .containsEntry("first", 1)
                .containsEntry("second", 2);
    }

    @Test
    void anOrderedUniqueListNeedsTwoAssertions() {
        List<String> actual = List.of("admin", "editor", "viewer");

        assertThat(actual).containsExactly("admin", "editor", "viewer");
        assertEquals(actual.size(), new HashSet<>(actual).size());
    }
}
```

Với các giá trị trên và phiên bản thư viện phù hợp, **cả sáu test đạt**. Chúng không in ra stdout; Maven/Gradle sẽ báo kết quả test theo runner và cấu hình của dự án. Một test đạt không chứng minh API hoặc repository thực của ứng dụng đã chạy, vì đây là các fixture collection trực tiếp trong test.

Chạy với Gradle wrapper (Linux/macOS):

```bash
./gradlew test --tests "com.example.testing.CollectionAssertionsTest"
```

Trên Windows PowerShell dùng `.\gradlew.bat test --tests "com.example.testing.CollectionAssertionsTest"`.

Với Maven wrapper:

```bash
./mvnw -Dtest=CollectionAssertionsTest test
```

Trên Windows PowerShell dùng `.\mvnw.cmd -Dtest=CollectionAssertionsTest test`. Các lệnh giả định dự án đã thiết lập JUnit Platform/Surefire thích hợp; thông tin lớp test được chọn phải được xác minh ở report của lần chạy thật.

### Một phản ví dụ: test xanh nhưng không phát hiện thiếu dữ liệu

```java
List<String> expected = List.of("A", "A", "B");
List<String> actual = List.of("A", "B");

boolean misleading = actual.containsAll(expected); // true!
```

Lý do: cả `"A"` và `"B"` đều có trong `actual`; `containsAll` không yêu cầu đủ **hai lượt `"A"`**. Nếu nghiệp vụ cần giữ duplicate, hãy dùng `containsExactlyInAnyOrder("A", "A", "B")` hoặc so sánh danh sách đã sắp xếp phù hợp mà không làm mất số lần xuất hiện.

Một phản ví dụ khác:

```java
List<String> actual = List.of("A", "A", "B");
Set<String> normalized = new HashSet<>(actual);

boolean missingEvidence =
        normalized.equals(Set.of("A", "B")); // true
```

Chuyển `List` sang `Set` đã làm mất thông tin có **hai chữ `"A"`**. Đừng “chuẩn hóa” theo kiểu này nếu duplicate là dữ liệu có ý nghĩa.

## 5. Kiểm tra thứ tự khi hợp đồng thực sự yêu cầu thứ tự

Danh sách thứ tự quan trọng khi API công bố sắp xếp theo thời gian, điểm số, mức độ ưu tiên, hoặc khi một chuỗi sự kiện phải xảy ra theo trình tự.

Ví dụ API `GET /orders?sort=createdAt,desc` hứa trả đơn hàng mới nhất trước. Với đầu ra đã ánh xạ thành ID theo thứ tự:

```java
List<Long> actualIds = List.of(103L, 102L, 101L);
assertThat(actualIds).containsExactly(103L, 102L, 101L);
```

Đối với test tích hợp/repository, hãy tạo dữ liệu có timestamp rõ ràng, thêm tiêu chí phụ nếu có trường hợp đồng thời điểm, và yêu cầu query thực hiện sắp xếp (`ORDER BY`, `Sort`, `Pageable`) theo hợp đồng. Không nên dùng thứ tự ngẫu nhiên của database làm expected value.

Nếu hợp đồng chỉ nói “trả các đơn hàng khớp điều kiện” mà không bảo đảm thứ tự, assertion `containsExactly` có thể khiến test đỏ vô lý khi hệ thống vẫn trả đúng tập kết quả. Trong trường hợp đó, dùng `containsExactlyInAnyOrder` khi số lần xuất hiện quan trọng, hoặc so sánh tập ID khi các ID phải duy nhất và thứ tự không quan trọng.

**Cảnh báo:** `assertIterableEquals` trên hai `HashSet` dễ tạo assertion phụ thuộc thứ tự duyệt không được bảo đảm. Để so hai `Set` theo nội dung, dùng `assertEquals(expectedSet, actualSet)` hoặc assertion tập hợp thích hợp.

## 6. Xác định rõ hợp đồng với phần tử trùng

Một collection chứa duplicate không nhất thiết sai:
- Giỏ hàng có thể chứa nhiều dòng cùng SKU nếu nghiệp vụ lưu từng sự kiện thêm hàng.
- Log sự kiện có thể chứa hai lần cùng tên event.
- Kết quả `JOIN` sai có thể vô tình nhân đôi bản ghi trong danh sách trả về.
- Danh sách quyền hoặc nhãn *có thể* yêu cầu mỗi giá trị xuất hiện một lần.

Với output cho phép duplicate nhưng không cam kết thứ tự, **số lần xuất hiện là một phần của hợp đồng**. AssertJ `containsExactlyInAnyOrder` kiểm tra số lượng phần tử tương ứng, vì vậy:

```java
List<String> actual = List.of("item-2", "item-1", "item-1");

assertThat(actual)
        .containsExactlyInAnyOrder("item-1", "item-1", "item-2");
```

Nếu bỏ một `"item-1"` hoặc thêm một `"item-2"`, assertion trên sẽ thất bại.

`containsOnly("item-1", "item-2")` chỉ thích hợp khi số lần lặp **không cần xác minh**. Với `Set`, duplicate luôn bị loại theo quy tắc bằng nhau của `Set`; không thể dùng set equality để phát hiện việc một query phát sinh hai dòng giống nhau trước khi biến đổi thành `Set`.

Nếu hợp đồng yêu cầu mỗi giá trị chỉ xuất hiện một lần, hãy xác nhận điều đó rõ ràng, ví dụ:

```java
List<String> actual = List.of("READ", "WRITE");
assertEquals(actual.size(), new HashSet<>(actual).size());
```

Đối với danh sách chứa object, tính duy nhất có thể theo **business key** (ví dụ `orderId`), không nhất thiết theo toàn bộ object `equals`. Khi đó trích xuất key rồi so sánh số lượng key duy nhất hoặc tính tần suất trên key. Chọn đúng khái niệm “trùng” theo nghiệp vụ.

## 7. Phân biệt tập rỗng, null, không có key và kết quả bị lọc hết

Một danh sách rỗng `[]` thường mang nghĩa “đã xử lý yêu cầu, không tìm thấy phần tử”; còn `null` có thể biểu thị “chưa có giá trị” hoặc vi phạm hợp đồng. Chúng **không đồng nghĩa**.

```java
List<String> emptyResult = List.of();

assertNotNull(emptyResult);
assertTrue(emptyResult.isEmpty());
assertThat(emptyResult).isEmpty();
assertEquals(List.of(), emptyResult);
```

Nếu giá trị có thể là `null` theo hợp đồng, kiểm tra rõ `assertNull(actual)`; không viết `actual.isEmpty()` khi nó có thể null vì sẽ ném `NullPointerException`. Với `Optional<List<T>>`, phân biệt `Optional.empty()` và `Optional.of(List.of())` khi nghiệp vụ có ý nghĩa khác nhau.

Với `Map`, **khóa không tồn tại** khác với **khóa tồn tại nhưng giá trị là null** đối với implementation cho phép null, ví dụ `HashMap`. `map.get(key) == null` không đủ để phân biệt; dùng `containsKey(key)` khi hợp đồng cần biết khóa có hiện diện.

Đối với API Spring Boot:
- Không có kết quả tìm kiếm có thể trả HTTP 200 và `[]`, nếu đó là hợp đồng API.
- Một resource đơn lẻ không tồn tại có thể cần HTTP 404; đây là trường hợp khác với danh sách rỗng.
- HTTP 204 không có response body; đừng cố parse `[]` từ body khi hợp đồng là không có nội dung.
- Khi dùng `MockMvc` hoặc test HTTP, cần kiểm tra cả status, JSON shape và nội dung. Một assertion vào collection Java đã deserialize **chưa tự chứng minh** status và JSON nguyên gốc đúng.

Không nên tự quyết một quy ước chung cho mọi endpoint; lấy expected behavior từ hợp đồng cụ thể rồi viết assertion tương ứng.

## 8. Khi phần tử là object/DTO: `equals` có thể làm test sai hoặc quá giòn

Ví dụ một service trả về `List<OrderDto>`. `List.equals` so sánh từng element bằng `equals`, nên nếu `OrderDto` là class Java thông thường không override `equals`, hai object cùng trường dữ liệu có thể vẫn khác nhau do tham chiếu.

Một cách đơn giản cho DTO không cần hành vi mutable phức tạp là dùng record:

```java
record OrderSummary(long id, String status) {}

List<OrderSummary> expected = List.of(
        new OrderSummary(1L, "PAID"),
        new OrderSummary(2L, "PENDING")
);
List<OrderSummary> actual = List.of(
        new OrderSummary(1L, "PAID"),
        new OrderSummary(2L, "PENDING")
);

assertEquals(expected, actual); // true: record so sánh component
```

Đây là **đoạn mã minh họa đặt trong phạm vi lớp hoặc phương thức có import `java.util.List` và `assertEquals`**; không phải một tệp Java độc lập như ví dụ test đầy đủ ở mục 4.

Nếu hợp đồng chỉ quan tâm các trường `id` và `status` mà không quan tâm metadata nội bộ, có thể trích xuất đúng các trường công khai hoặc dùng AssertJ `extracting`. Tránh kiểm tra `toString()`, serialize JSON thủ công rồi so chuỗi (có thể phụ thuộc thứ tự thuộc tính), hoặc so reference identity khi mục tiêu là so giá trị.

Nếu phần tử tự thân là mảng, `List<byte[]>.equals` sẽ so sánh reference của từng mảng, không so sâu nội dung byte. Khi nội dung mảng là điều cần bảo vệ, dùng `assertArrayEquals` cho mảng hoặc chuyển dữ liệu sang kiểu có equality đúng nghĩa.

## 9. So sánh Map: thứ tự không quan trọng nhưng từng khóa và giá trị quan trọng

`Map.equals` xác minh rằng hai map có cùng số entry và mỗi khóa ánh xạ đến giá trị bằng nhau. Thứ tự thêm vào `LinkedHashMap` không làm chúng khác nhau khi dùng `equals`.

```java
Map<String, Integer> expected = Map.of("OPEN", 2, "CLOSED", 1);

Map<String, Integer> actual = new LinkedHashMap<>();
actual.put("CLOSED", 1);
actual.put("OPEN", 2);

assertEquals(expected, actual);
assertThat(actual).containsEntry("OPEN", 2);
```

Đây là đoạn minh họa trong phạm vi có import `Map`, `LinkedHashMap` và assertions. Nếu test chỉ dùng `containsEntry("OPEN", 2)`, nó không chứng minh map **không có các entry thừa**; dùng `assertEquals(expected, actual)` hoặc assertion kiểm tra đầy đủ khi hợp đồng yêu cầu khớp toàn bộ.

Map không cho hai entry có cùng khóa trong cùng một thời điểm: `put` cùng khóa lần nữa **ghi đè** giá trị cũ. Vì vậy, nếu lỗi liên quan số dòng dữ liệu trùng khóa trước khi gom nhóm, cần kiểm tra dữ liệu trước bước gom map hoặc dùng cấu trúc giữ được multiplicity.

## 10. Tình huống thực tế trong Spring Boot: chọn mức kiểm thử và assertion

| Tình huống | Hợp đồng cần chứng minh | Assertion trọng tâm |
|---|---|---|
| `GET /orders` đã sắp xếp mới nhất trước | Thứ tự ID đúng, không thiếu/thừa | Danh sách ID `containsExactly(...)` |
| Repository `findByStatus` không bảo đảm sort | Cùng các đơn hàng, không phụ thuộc thứ tự | `containsExactlyInAnyOrder(...)` nếu số lần xuất hiện quan trọng |
| Danh sách ID đơn hàng phải duy nhất | Không có ID trùng | Size list bằng size set các ID, cùng nội dung mong đợi |
| Danh sách sự kiện cho phép trùng | Đúng số lần từng event | `containsExactlyInAnyOrder(...)` |
| Tập quyền của người dùng | Có đúng các quyền, không cần thứ tự | `assertEquals(expectedSet, actualSet)` |
| Không tìm thấy đơn hàng trong kết quả search | Trả danh sách rỗng theo hợp đồng | `assertNotNull` và `isEmpty()` |
| Tổng hợp số lượng theo trạng thái | Từng khóa ánh xạ đúng count, không dư entry | `Map.equals` |
| JSON API phải trả array theo thứ tự | HTTP status và JSON array đúng vị trí | Assertion MockMvc/JSON path theo index hoặc deserialize rồi `containsExactly` |
| Không có phần tử trong response API | HTTP/status/shape theo hợp đồng | Kiểm tra status, body `[]` hay không body đúng yêu cầu |

**Chú ý về database và collection order:** nếu truy vấn JPA/SQL không có ràng buộc sắp xếp, thứ tự bản ghi không được bảo đảm. Không viết test mong đợi một thứ tự “tình cờ thấy” trên H2 hoặc PostgreSQL. Nếu sản phẩm yêu cầu thứ tự, hãy đưa order vào truy vấn/`Sort` và kiểm tra nó. Nếu không, dùng assertion không phụ thuộc thứ tự nhưng vẫn xác nhận đầy đủ số lượng và phần tử.

**Chú ý về `@SpringBootTest`:** khởi tạo Spring context không làm các quy tắc equality thay đổi. Chỉ dùng test tích hợp khi cần xác minh mapping, repository, database hoặc hợp đồng HTTP. Với hàm so collection thuần Java, JUnit unit test thông thường thường đủ nhanh và dễ hiểu.

## 11. Những lỗi assertion thường gặp

| Sai lầm | Vì sao sai | Cách sửa |
|---|---|---|
| So `List` bằng `containsAll` | Bỏ qua thứ tự, phần tử thừa và duplicate count | `assertEquals`, `containsExactly` hoặc `containsExactlyInAnyOrder` tùy hợp đồng |
| Chuyển list thành set trước khi so dù cần biết duplicate | Làm mất số lần xuất hiện | Giữ list và kiểm tra multiplicity |
| `assertIterableEquals` trên `HashSet` | Thứ tự duyệt không ổn định/không thuộc hợp đồng | So nội dung set qua `assertEquals` |
| `containsOnly` để xác nhận mỗi phần tử xuất hiện đúng một lần | Không xác minh số lần lặp | Dùng `containsExactlyInAnyOrder` hoặc count cụ thể |
| Chỉ `contains("A")` với output phải có đúng một phần tử | Không bắt phần tử thừa | `containsExactly("A")` |
| Assert danh sách rỗng khi code trả `null` | `null` khác empty | Assert non-null và `isEmpty`; hoặc `assertNull` nếu hợp đồng yêu cầu |
| So `List<DTO>` nhưng DTO thiếu equality theo dữ liệu | So reference thay vì nội dung | Dùng record, equality phù hợp hoặc trích xuất trường cần assert |
| So map theo thứ tự `toString()` | `Map` thường không cam kết thứ tự duyệt | So entry bằng `Map.equals` |
| Tưởng `Set.of("A", "A")` tạo set một phần tử | `Set.of` từ chối duplicate bằng `IllegalArgumentException` | Cung cấp phần tử duy nhất, hoặc dùng construction phù hợp nếu muốn test loại trùng |
| Chỉ assert kích thước | Cùng kích thước vẫn có thể sai phần tử hoặc thứ tự | Kiểm tra nội dung đầy đủ theo hợp đồng |

## 12. Checklist trước khi chốt bài test collection

- [ ] Đã biết kiểu kết quả là `List`, `Set`, `Map`, array hay `Iterable` tùy biến.
- [ ] Đã xác nhận thứ tự có thuộc hợp đồng hay chỉ là thứ tự xuất hiện tình cờ.
- [ ] Đã xác nhận duplicate có ý nghĩa và số lần xuất hiện có cần chính xác không.
- [ ] Assertion kiểm tra đủ phần tử; không bỏ sót phần tử thừa hoặc thiếu.
- [ ] Nếu kết quả yêu cầu duy nhất, đã kiểm tra uniqueness theo đúng business key.
- [ ] Đã phân biệt `null`, tập rỗng, key vắng mặt và API body trống theo yêu cầu.
- [ ] Với object/DTO, equality dựa trên dữ liệu cần bảo vệ, không phụ thuộc tham chiếu tình cờ.
- [ ] Với repository/API, đã tách yêu cầu sắp xếp khỏi thứ tự không được bảo đảm.
- [ ] Test ổn định khi chạy lại trên máy khác/CI; không dựa vào iteration order của hash collection.
- [ ] Đã chạy đúng test và xem report trước khi tuyên bố pass đối với mã ứng dụng thực.

**Kết luận:** Khi so sánh collection trong Spring Boot, hãy xác định **thứ tự có quan trọng không**, **số lần xuất hiện có quan trọng không**, và **rỗng có khác null không**. `List.equals` và `containsExactly` phù hợp cho thứ tự chính xác; `containsExactlyInAnyOrder` giữ đúng số lần lặp nhưng bỏ qua thứ tự; `Set.equals` và `Map.equals` phù hợp khi thứ tự không thuộc hợp đồng. Assertion tốt phải phát hiện cả kết quả thiếu, thừa và sai cấu trúc theo đúng yêu cầu nghiệp vụ.