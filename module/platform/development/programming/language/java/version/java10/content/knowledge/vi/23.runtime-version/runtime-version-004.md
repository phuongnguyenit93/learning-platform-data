# Danh sách thành phần số của phiên bản với `Runtime.Version.version()` (Java 10+)

## 1. Vì sao phải hiểu “các thành phần số” của phiên bản Java?

Khi ứng dụng cần ghi log phiên bản JVM, kiểm tra bản Java tối thiểu hoặc so sánh hai bản phát hành, việc chỉ nhìn chuỗi như `"21.0.1+12-LTS"` rất dễ dẫn đến sai lầm. Chuỗi phiên bản có **phần số** và có thể có **thông tin phát hành sớm / build / định danh bổ sung**; không phải mọi ký tự trong chuỗi đều là một số phiên bản.

Java cung cấp class `java.lang.Runtime.Version` để biểu diễn version string của bản triển khai Java SE. Phương thức trọng tâm:

```java
public List<Integer> version()
```

trả về **một danh sách không cho chỉnh sửa** các số nguyên xuất hiện trong **version number** (`$VNUM`). Danh sách này:

- Có kiểu `List<Integer>`.
- Chứa **ít nhất một phần tử**: số `feature`.
- Giữ **thứ tự từ trái sang phải** của các thành phần số trong `$VNUM`.
- Chứa các số **0 ở giữa** nếu chúng được ghi trong version number.
- **Không** tự chèn số 0 vào cuối để thành danh sách đủ bốn phần tử.
- **Không** chứa phần `pre-release`, `build` hay `optional`.
- Không cho phép thêm, xóa hoặc thay đổi các phần tử qua danh sách trả về.

Ví dụ:

```java
Runtime.Version v = Runtime.Version.parse("21.0.1+12-LTS");
List<Integer> components = v.version();

System.out.println(components); // [21, 0, 1]
System.out.println(v.feature()); // 21
System.out.println(v.update());  // 1
```

Đoạn minh họa cần `import java.util.List;`. Chuỗi `+12-LTS` có dữ liệu build/optional, nhưng **không xuất hiện trong `components`**.

Đây là bài thuộc ngữ cảnh **`Runtime.Version`** trong module Java 10. `Runtime.Version` bắt đầu có trong Java 9; mô hình tên thành phần **`feature / interim / update / patch`** được điều chỉnh theo **JEP 322 của Java 10**, và các API mô tả dưới đây vẫn áp dụng trong Java hiện đại. Bài **không** dùng các tên accessor cũ đã deprecated như `major()`, `minor()` hoặc `security()`.

## 2. Kết quả học tập

Sau khi học, bạn có thể:

1. Đọc đúng kiểu và hợp đồng của `Runtime.Version.version()`.
2. Phân biệt `version string`, `version number` và `List<Integer>`.
3. Diễn giải bốn vị trí chính: `FEATURE`, `INTERIM`, `UPDATE` và `PATCH`.
4. Hiểu vì sao `"21.0.1"` sinh `[21, 0, 1]` chứ không phải `[21, 0, 1, 0]`.
5. Biết số 0 ở **giữa** hợp lệ, còn số 0 ở **cuối** version number không hợp lệ.
6. Dùng `feature()`, `interim()`, `update()`, `patch()` để đọc thành phần có tên và giá trị mặc định 0 khi thiếu.
7. Duyệt danh sách số và kiểm tra `size()` để tránh `IndexOutOfBoundsException`.
8. Hiểu danh sách là **unmodifiable**, không phải danh sách dùng để sửa phiên bản.
9. Phân biệt các thông tin `pre()`, `build()`, `optional()` với phần số.
10. So sánh phiên bản đúng bằng `compareTo` thay vì so sánh chuỗi theo từ điển.
11. Hiểu khác biệt giữa so sánh **chỉ phần số** và so sánh **toàn bộ Runtime.Version**.
12. Dùng `Runtime.version()` để quan sát JVM hiện tại nhưng kiểm thử bằng `Runtime.Version.parse(...)` với chuỗi cố định.
13. Tránh giả định mọi chuỗi phiên bản Java đều có đúng bốn số hoặc mọi chữ số đều mang cùng ý nghĩa.
14. Nhận diện version string không hợp lệ, giới hạn của version gating và lỗi khi dùng metadata build.
15. Chạy một chương trình Java 17+ kiểm chứng toàn bộ các trường hợp trên.

## 3. Phân biệt version string và version number

Một chuỗi phiên bản (`version string`) có thể gồm:

```text
21.0.1+12-LTS
│────┘│  └─ optional build information: LTS
│     └──── build number: 12
└────────── version number ($VNUM): 21.0.1
```

Với ví dụ trên:

- `$VNUM`: `21.0.1`.
- Các thành phần số: `21`, `0`, `1`.
- `build()`: `Optional.of(12)`.
- `optional()`: `Optional.of("LTS")`.
- `pre()`: `Optional.empty()`.

`version()` chỉ trả **`[21, 0, 1]`**. Số build 12 tuy là một số nhưng **không phải một thành phần trong version number**; nó nằm trong phần thông tin build riêng của version string.

Một dạng khác:

```text
21-ea+7
│  │  └─ build = 7
│  └──── pre-release = ea
└─────── version number = 21
```

Tức là:

```java
var early = Runtime.Version.parse("21-ea+7");

System.out.println(early.version()); // [21]
System.out.println(early.pre().orElse("none")); // ea
System.out.println(early.build().orElse(-1));   // 7
```

Danh sách số chỉ có **một** phần tử, dù chuỗi có thêm số `7` ở cuối phần build.

**Quy tắc:** đừng “đếm tất cả chữ số bằng regex” rồi gọi đó là danh sách thành phần số; cú pháp `$VNUM` và các hậu tố có ngữ nghĩa khác nhau.

## 4. Hợp đồng `version()`: danh sách có thứ tự và không sửa được

Chữ ký trên Javadoc:

```java
public List<Integer> version()
```

Hai điều được cam kết quan trọng:

1. Trả về một `List` **unmodifiable**.
2. `List` **luôn chứa ít nhất một phần tử** tương ứng với `feature version number`.

Ví dụ:

```java
Runtime.Version parsed = Runtime.Version.parse("17.0.8");
List<Integer> numbers = parsed.version();

System.out.println(numbers);        // [17, 0, 8]
System.out.println(numbers.size()); // 3
System.out.println(numbers.get(0)); // 17
System.out.println(numbers.get(2)); // 8
```

`List<Integer>` khác với `int[]`: gọi `numbers.get(0)` để truy cập, không viết `numbers[0]`. Các phần tử được đóng hộp ở kiểu `Integer`; khi dùng trong số học, Java có thể tự unbox thành `int`.

### Danh sách không cho thêm hoặc thay phần tử

```java
var numbers = Runtime.Version.parse("21.0.1").version();

// numbers.add(2);    // UnsupportedOperationException
// numbers.set(0, 99); // UnsupportedOperationException
```

Các dòng được comment vì chúng **ném ngoại lệ khi chạy**, không phải lỗi cú pháp Java. Chương trình độc lập ở mục 16 thử và bắt cả hai ngoại lệ để xác nhận hợp đồng.

Đừng dựa vào class triển khai `List` cụ thể hay identity của danh sách. Nếu một đoạn logic thật sự cần danh sách **mutable** để thao tác riêng:

```java
var copy = new java.util.ArrayList<Integer>(
        Runtime.Version.parse("21.0.1").version());

copy.add(99); // Chỉ sửa bản copy, không sửa Runtime.Version
```

Việc chỉnh bản copy không tạo ra một `Runtime.Version` mới và không thay đổi phiên bản Java đang chạy.

### Có thể gọi `get(0)` không?

Có. Danh sách luôn có ít nhất một phần tử. Nhưng **không được** cho rằng `get(1)`, `get(2)`, `get(3)` đều hợp lệ: nếu chuỗi chỉ có `"21"` thì list chỉ có một phần tử.

## 5. Bốn thành phần có tên: `FEATURE.INTERIM.UPDATE.PATCH`

Từ mô hình phát hành theo thời gian ở Java 10, bốn vị trí đầu của version number có tên:

```text
$FEATURE.$INTERIM.$UPDATE.$PATCH
    21  .   0   .   1   .   2
     │      │       │       │
     └──────┼───────┼───────┼─ Feature: chu kỳ phát hành tính năng
            └───────┼───────┼─ Interim: đợt phát hành trung gian
                    └───────┼─ Update: sửa lỗi/bảo mật và cập nhật
                            └─ Patch: bản vá khẩn cấp
```

Sơ đồ giải thích tên vị trí, không cho biết phiên bản `21.0.1.2` có phải một bản phân phối chính thức nhất định hay không.

| Vị trí list | Accessor có tên | Ý nghĩa chính | Nếu không có vị trí đó |
| --- | --- | --- | --- |
| `get(0)` | `feature()` | Feature release counter | Không thể thiếu |
| `get(1)` | `interim()` | Interim release counter | Trả `0` qua accessor |
| `get(2)` | `update()` | Update release counter | Trả `0` qua accessor |
| `get(3)` | `patch()` | Emergency patch release counter | Trả `0` qua accessor |

Ví dụ:

```java
var v = Runtime.Version.parse("21.0.1");

System.out.println(v.feature()); // 21
System.out.println(v.interim()); // 0
System.out.println(v.update());  // 1
System.out.println(v.patch());   // 0
```

Ở đây:

- `version()` trả `[21, 0, 1]` (**3 phần tử**).
- `patch()` trả 0 vì thành phần thứ tư **không có mặt**.
- `v.version().get(3)` sẽ ném `IndexOutOfBoundsException`.

Hai cách truy cập có hợp đồng khác nhau:

- Muốn lấy **giá trị theo tên** và chấp nhận 0 khi thiếu → `feature()/interim()/update()/patch()`.
- Muốn biết **những thành phần nào được ghi rõ** trong `$VNUM` → `version()` và `size()`.

### Ý nghĩa hiện hành của `INTERIM`

Theo mô hình phát hành sáu tháng của Java, interim thường bằng 0 và vị trí này được dành cho khả năng thay đổi mô hình trong tương lai. Không được dùng `interim()` để đoán “phiên bản phụ” theo cách đánh số phần mềm tùy ý hoặc đồng nhất nó với mức tương thích SemVer của thư viện ứng dụng.

### Vì sao không dùng `major()/minor()/security()`?

Các accessor này tồn tại vì tương thích lịch sử nhưng đã **deprecated** sau khi Java 10 chuyển cách diễn giải tên vị trí. Bài chỉ dạy các accessor **`feature()/interim()/update()/patch()`** còn được khuyến nghị, tránh viết code mới dựa vào tên cũ và ý nghĩa không phù hợp.

## 6. Ví dụ bảng: version number sinh danh sách ra sao?

| Chuỗi parse | `version()` | `feature()` | `interim()` | `update()` | `patch()` |
| --- | --- | ---: | ---: | ---: | ---: |
| `10` | `[10]` | 10 | 0 | 0 | 0 |
| `17.0.8` | `[17, 0, 8]` | 17 | 0 | 8 | 0 |
| `21.0.1` | `[21, 0, 1]` | 21 | 0 | 1 | 0 |
| `21.0.0.1` | `[21, 0, 0, 1]` | 21 | 0 | 0 | 1 |
| `21.0.1.2.3` | `[21, 0, 1, 2, 3]` | 21 | 0 | 1 | 2 |
| `21-ea+7` | `[21]` | 21 | 0 | 0 | 0 |
| `21.0.1+12-LTS` | `[21, 0, 1]` | 21 | 0 | 1 | 0 |

Bảng bao gồm **dữ liệu parse minh họa**, không khẳng định tất cả các chuỗi đó là tên của một bản JDK GA chính thức được phát hành.

Đặc biệt:

- `"10"` → một phần tử, **không** phải `[10, 0, 0, 0]`.
- `"21.0.1"` → ba phần tử, **không** phải bốn.
- `"21.0.0.1"` → giữ hai số 0 trung gian.
- `"21.0.1.2.3"` → **năm phần tử**; phần tử thứ năm có ý nghĩa theo bên phân phối, không được gộp nó vào `patch()`.
- `"21-ea+7"` → `pre` và `build` không thuộc list.
- `"21.0.1+12-LTS"` → dù chứa 12, list chỉ có ba phần tử.

## 7. Ngữ pháp `$VNUM`: không có số 0 kết thúc

Version number là dãy số nguyên không âm, phân cách bằng dấu chấm, với các giới hạn:

- Phần tử đầu tiên **lớn hơn 0**.
- Mỗi phần tử hoặc bằng `0`, hoặc là một số nguyên dương **không có số 0 đứng đầu**.
- **Phần tử cuối không được bằng 0**.
- Danh sách có thể dài hơn bốn số; bốn số đầu có tên chuẩn, các phần sau dành cho downstream implementors.

Các ví dụ hợp lệ:

```text
10
17.0.8
21.0.1
21.0.0.1
21.0.1.2.3
```

Các ví dụ không hợp lệ:

```text
21.0         # kết thúc bằng 0
17.0.0       # kết thúc bằng 0
01           # số đầu có leading zero
21..1        # thiếu phần tử giữa hai dấu chấm
21.0.01      # phần tử 01 có leading zero
```

**Vì sao `21.0.0.1` hợp lệ nhưng `21.0.0` không?** Vì các số 0 ở giữa thể hiện đúng vị trí của phần tử đứng sau. Ở `21.0.0.1`, phần tử cuối là `1`, không phải `0`. Ở `21.0.0`, phần tử cuối là 0 nên không hợp lệ theo version-number syntax.

### Không tự điền các số 0 bị thiếu

`version()` giữ **các phần tử được biểu diễn trong chuỗi**. `patch()==0` khi thiếu **không** có nghĩa có một phần tử thứ tư bằng 0 trong list. Đừng viết code như:

```java
var v = Runtime.Version.parse("21.0.1");

// Có 3 phần tử:
// v.version().get(3); // IndexOutOfBoundsException

int patch = v.patch(); // 0, hợp lệ
```

Nếu cần một mảng 4 số để kết nối với schema bên ngoài, **bạn** có thể tạo dữ liệu mới từ bốn accessor có tên. Nhưng phân biệt đó là **biểu diễn do ứng dụng chuẩn hóa**, không phải nội dung gốc `version()` và không phải version string hợp lệ nếu sau đó nối thành `"21.0.1.0"`.

## 8. Nếu có hơn bốn thành phần số thì sao?

JEP 322 xác định bốn vị trí đầu cho mô hình Java, còn **vị trí thứ năm trở đi** dành cho bên phân phối/downstream consumers.

Ví dụ:

```java
var v = Runtime.Version.parse("21.0.1.2.3");

System.out.println(v.version());        // [21, 0, 1, 2, 3]
System.out.println(v.version().size()); // 5
System.out.println(v.patch());          // 2
System.out.println(v.version().get(4)); // 3
```

Phần tử thứ năm có index 4, **không phải** giá trị trả từ `patch()`. Ý nghĩa cụ thể của `3` là việc của bản phân phối định nghĩa, không có quy tắc “nó luôn là hotfix” áp dụng cho mọi JDK.

Cách xử lý trong phần mềm:

- Với nhu cầu biết Java feature/update/patch → dùng accessor có tên.
- Với nhu cầu lưu/hiển thị **toàn bộ dãy số** → dùng `version()`.
- Với dữ liệu vendor-specific ở vị trí 5 trở đi → chỉ gán ý nghĩa sau khi có tài liệu của vendor tương ứng.
- Không viết `if (list.size() == 4)` như điều kiện bắt buộc cho mọi Java version.
- Nếu code của bạn chỉ hỗ trợ một số định dạng, hãy kiểm hợp đồng đầu vào và báo lỗi rõ, thay vì bỏ silently những phần còn lại.

## 9. `pre()`, `build()` và `optional()` là những thành phần riêng

Ngoài `$VNUM`, version string có thể chứa:

- **Pre-release identifier**: ví dụ `ea` (early access).
- **Build number**: ví dụ `+7` hoặc `+12`.
- **Optional build information**: ví dụ `-LTS` sau phần build phù hợp.

API hiện hành:

| API | Kiểu trả về | Ví dụ |
| --- | --- | --- |
| `version()` | `List<Integer>` | `[21, 0, 1]` |
| `pre()` | `Optional<String>` | `Optional[ea]` hoặc `Optional.empty` |
| `build()` | `Optional<Integer>` | `Optional[12]` hoặc `Optional.empty` |
| `optional()` | `Optional<String>` | `Optional[LTS]` hoặc `Optional.empty` |

Ví dụ:

```java
var ea = Runtime.Version.parse("21-ea+7");
System.out.println(ea.version());             // [21]
System.out.println(ea.pre().orElse("none"));   // ea
System.out.println(ea.build().orElse(-1));     // 7

var lts = Runtime.Version.parse("21.0.1+12-LTS");
System.out.println(lts.version());            // [21, 0, 1]
System.out.println(lts.pre().isEmpty());       // true
System.out.println(lts.build().orElse(-1));    // 12
System.out.println(lts.optional().orElse("none")); // LTS
```

**Không nên nối cả các số trong `pre/build/optional` vào `version()`.** Điều đó làm đổi ngữ nghĩa của đối tượng. Ví dụ `21-ea+7` **không** phải dãy số `[21, 7]`.

### Thông tin `LTS` không phải cơ chế kiểm tra hỗ trợ bảo mật

Chuỗi `optional()` có thể chứa thông tin nhận diện bản phân phối, như `LTS`, nhưng **không** tự cung cấp lịch bảo trì, thời hạn hỗ trợ hay tình trạng vá lỗ hổng của JDK tại thời điểm hiện tại. Những thông tin đó thuộc chính sách và kênh phát hành của nhà cung cấp JDK.

## 10. Đọc an toàn: `List.get(index)` hay accessor có tên?

### Khi bạn cần dãy số đúng như được ghi

```java
Runtime.Version v = Runtime.Version.parse("21.0.1");
List<Integer> numbers = v.version();

for (int i = 0; i < numbers.size(); i++) {
    System.out.println(i + ": " + numbers.get(i));
}
```

Stdout:

```text
0: 21
1: 0
2: 1
```

Dùng vòng lặp `i < numbers.size()` nên không vượt index, bất kể dãy có 1, 3, 4 hay 5 phần tử. Java 10 có `var` nhưng việc dùng kiểu `List<Integer>` tường minh trong ví dụ cũng hoàn toàn hợp lệ ở các phiên bản hiện đại.

### Khi bạn cần một trong bốn vai trò chính

```java
Runtime.Version v = Runtime.Version.parse("21.0.1");

int feature = v.feature();
int update = v.update();
int patch = v.patch();

System.out.println(feature); // 21
System.out.println(update);  // 1
System.out.println(patch);   // 0
```

Nhờ accessor có tên, code không cần tự xử lý việc thiếu thành phần 4.

### Nếu nghiệp vụ muốn biết “có ghi rõ patch không?”

`v.patch()==0` không thể trả lời liệu vị trí thứ tư có **xuất hiện tường minh** hay không. Với định dạng `$VNUM` hợp lệ, phần tử cuối không bằng 0, nhưng ý nghĩa kiểm tra metadata nên dựa vào sự **hiện diện**:

```java
boolean hasExplicitFourthComponent =
        v.version().size() >= 4;
```

Còn nếu chỉ cần **giá trị** patch, dùng `patch()`.

### Không truy cập index cố định khi danh sách chưa đủ dài

```java
var shortVersion = Runtime.Version.parse("10");

// shortVersion.version().get(2); // Ném IndexOutOfBoundsException
int update = shortVersion.update(); // 0
```

Đây là lỗi thường gặp nếu tự giả định version number luôn gồm bốn phần.

## 11. So sánh phiên bản: vì sao không so chuỗi trực tiếp?

So sánh chuỗi theo từ điển không tương đương so sánh số:

```text
"21.0.9"
"21.0.10"
```

Khi so theo chữ, ký tự `9` có thể được đánh giá sau `1` ở vị trí tương ứng; nhưng về mặt số học, 9 **nhỏ hơn** 10.

Dùng `Runtime.Version.compareTo`:

```java
var a = Runtime.Version.parse("21.0.9");
var b = Runtime.Version.parse("21.0.10");

System.out.println(a.compareTo(b) < 0); // true
```

Javadoc mô tả việc so sánh version theo thứ tự:

1. Dãy **thành phần số**.
2. `pre-release` identifier.
3. Số `build`.
4. Thông tin `optional`, trừ khi dùng phương thức chủ động bỏ qua nó.

Các số được so **theo giá trị số nguyên**, từ trái qua phải. Nếu một dãy ngắn hơn dãy kia, các thành phần thiếu ở cuối dãy ngắn được xem là nhỏ hơn các thành phần tương ứng của dãy dài trong so sánh.

### Ví dụ bản phát hành sớm

```java
var preview = Runtime.Version.parse("21-ea+7");
var release = Runtime.Version.parse("21");

System.out.println(preview.version()); // [21]
System.out.println(release.version()); // [21]
System.out.println(preview.compareTo(release) < 0); // true
```

Dù **danh sách số giống nhau**, bản `pre-release` được xếp trước bản không có `pre-release` khi so sánh toàn bộ version theo API.

**Đừng so `version().equals(...)` để suy ra hai Runtime.Version tương đương toàn bộ.**

## 12. `compareToIgnoreOptional` và `equalsIgnoreOptional`

Thông tin optional build metadata có thể làm hai đối tượng cùng dãy số và cùng build number được phân biệt theo `compareTo`.

```java
var a = Runtime.Version.parse("21.0.1+12");
var b = Runtime.Version.parse("21.0.1+12-LTS");

System.out.println(a.version().equals(b.version())); // true
System.out.println(a.compareTo(b) < 0);              // true
System.out.println(a.compareToIgnoreOptional(b));    // 0
System.out.println(a.equalsIgnoreOptional(b));       // true
```

Ý nghĩa:

- `version()` của hai đối tượng đều là `[21, 0, 1]`.
- `compareTo` tính đến phần `optional` và do đó có thể cho kết quả khác 0.
- `compareToIgnoreOptional` **chỉ bỏ qua optional build information**; không có nghĩa nó bỏ qua `pre`, `build` hoặc các thành phần số.
- `equalsIgnoreOptional` nên được dùng tương ứng nếu bạn so khớp đối tượng theo quy tắc bỏ optional.

Đừng kết hợp cách sắp xếp theo `compareToIgnoreOptional` với một tiêu chuẩn equality không tương ứng nếu điều kiện ứng dụng yêu cầu consistency. Đặc biệt, `TreeSet` và `TreeMap` sử dụng comparator để quyết định những phần tử/key “bằng nhau” trong cấu trúc đã sắp xếp.

### Khi nào dùng cách so sánh nào?

- Muốn thứ tự của version string **đầy đủ** → `compareTo`.
- Muốn không xét phần optional vendor information → `compareToIgnoreOptional`.
- Muốn kiểm phần số có cùng danh sách được viết ra → `version().equals(...)`, nhưng **chỉ đang xét phần số**.
- Muốn so khớp chính xác version string được parse thành đối tượng → `equals(...)`.

Hãy ghi rõ yêu cầu nghiệp vụ thay vì mặc định mọi cách so bằng nhau là một.

## 13. `Runtime.version()`: lấy phiên bản của JVM đang chạy

Đến đây các ví dụ dùng `Runtime.Version.parse("...")`. Khi cần biết phiên bản **của runtime thực sự**:

```java
Runtime.Version running = Runtime.version();

System.out.println(running.version());
System.out.println(running.feature());
```

**Không có stdout cố định** cho hai dòng trên: máy sử dụng JDK 17, 21, 26 hoặc một runtime khác có thể trả version number khác, gồm cả update, build, optional của bản phân phối.

### Viết test không phụ thuộc JDK cài ở máy người học

Thay vì:

```java
// Không nên cho unit test portable:
// assertEquals(List.of(17, 0, 10), Runtime.version().version());
```

hãy kiểm một invariant được Javadoc bảo đảm:

```java
var running = Runtime.version();
var list = running.version();

boolean nonEmpty = !list.isEmpty();
boolean firstIsFeature = list.get(0) == running.feature();
```

Trường hợp kiểm logic parse, dùng chuỗi kiểm thử **cố định**:

```java
var parsed = Runtime.Version.parse("21.0.1");
boolean correct = parsed.version().equals(
        java.util.List.of(21, 0, 1));
```

Phân biệt hai mục tiêu:

- **Unit test cho logic phân tích version**: `parse(...)` với input cố định → kết quả xác định.
- **Integration test quan sát JVM**: `Runtime.version()` → kết quả thật phụ thuộc runtime; chỉ assert điều kiện tương thích mà ứng dụng cần.

### Phiên bản JVM không phải compiler target

Chương trình được biên dịch với `javac --release 17` vẫn có thể chạy trên một JDK mới hơn. `Runtime.version()` báo **runtime đang thực thi**, không phải tự động báo giá trị `17` chỉ vì bạn đã dùng `--release 17`.

Không dùng `Runtime.version()` để suy luận phiên bản của thư viện, file class tải từ nơi khác hay version của ngôn ngữ Java mà developer đã chọn trong IDE.

## 14. Kiểm tra feature version: đúng nhưng không đủ cho mọi kiểm tra tương thích

Một nhu cầu phổ biến là kiểm tra mức Java feature tối thiểu:

```java
boolean suitableFeature = Runtime.version().feature() >= 17;
```

Phép kiểm này là **một điều kiện về runtime feature number**, giúp đưa ra thông báo hoặc chọn nhánh triển khai phù hợp ở runtime.

Nhưng cần hiểu:

- Nó **không thay thế** bước biên dịch ứng dụng cho một `--release` tương ứng.
- Nó không tự bảo đảm mọi class, method hoặc thư viện mà code sử dụng tồn tại trên runtime.
- Nó không bảo đảm bản JDK đã cập nhật bản vá bảo mật mới nhất.
- Nó không đánh giá chính sách hỗ trợ/LTS của nhà cung cấp.
- Nếu trong bytecode có tham chiếu trực tiếp tới API không tồn tại ở runtime thấp hơn, ứng dụng vẫn có thể gặp lỗi load/link trước khi một check chạy đúng cách.
- Một ứng dụng hỗ trợ nhiều Java feature levels cần thiết kế chiến lược biên dịch, class loading và kiểm thử integration đúng.

`feature()` rất thích hợp để đọc số feature, nhưng không phải một công cụ tổng quát để xác nhận mức tương thích của toàn hệ thống.

### Khi phải xử lý update cụ thể

`Runtime.Version.parse("17.0.12").update()` trả 12. Nhưng việc kiểm một mức update tối thiểu có thể còn cần cân nhắc patch, vendor, ngày phát hành và chính sách sản phẩm. Tránh một kiểm tra cứng bằng chuỗi `"17.0.12"` nếu runtime có thêm build/optional khác mà ứng dụng vẫn chấp nhận.

## 15. Đừng tách version string bằng `split("\\.")` rồi tự đoán

Một lối xử lý dễ sai:

```java
String text = "21.0.1+12-LTS";
// String[] parts = text.split("\\.");
// parts[2] == "1+12-LTS", KHÔNG phải số nguyên thuần!
```

Hậu tố `+12-LTS` xuất hiện bên cạnh thành phần số cuối, nên `Integer.parseInt(parts[2])` sẽ ném `NumberFormatException`. Mặt khác, số phần tử có thể là 1, 3, 4, 5..., và ngữ pháp cấm trailing zero.

**Thay vào đó:**

```java
Runtime.Version parsed = Runtime.Version.parse(text);
List<Integer> parts = parsed.version();
```

Javadoc của `parse` thực hiện kiểm tra cú pháp version string chính thức. Việc gọi `Integer.parseInt` từng token hoặc một regex tự chế không nên thay thế API chuẩn khi bạn đang xử lý **version string của Java SE Platform**.

### Phân biệt với Semantic Versioning của thư viện

`Runtime.Version` biểu diễn **version strings của Java SE Platform implementation** theo ngữ pháp Java, không phải parser SemVer tổng quát cho mọi thư viện như `1.2.3-alpha.1+meta`. Dù có phần giống nhau về dấu chấm và hậu tố, quy tắc có thể khác, nhất là cách so sánh build metadata hoặc định nghĩa các thành phần.

Nếu xử lý phiên bản của sản phẩm khác (Maven package, REST API, package.json), hãy theo đúng đặc tả của sản phẩm đó; không tự sử dụng `Runtime.Version.parse` cho mọi kiểu version string.

## 16. Chương trình Java 17+ độc lập để kiểm chứng

Tạo tệp **`RuntimeVersionComponentsDemo.java`**:

```java
import java.util.List;

public class RuntimeVersionComponentsDemo {
    static Runtime.Version parse(String text) {
        return Runtime.Version.parse(text);
    }

    static boolean rejects(String text) {
        try {
            parse(text);
            return false;
        } catch (IllegalArgumentException expected) {
            return true;
        }
    }

    public static void main(String[] args) {
        var ten = parse("10");
        var update = parse("21.0.1");
        var patched = parse("21.0.0.1");
        var extended = parse("21.0.1.2.3");
        var early = parse("21-ea+7");
        var vendor = parse("21.0.1+12-LTS");

        System.out.println("tenList=" + ten.version());
        System.out.println("updateList=" + update.version());
        System.out.println("patchedList=" + patched.version());
        System.out.println("extendedList=" + extended.version());
        System.out.println("updateListSize=" + update.version().size());
        System.out.println("firstComponent=" + update.version().get(0));
        System.out.println("namedUpdate="
                + update.feature() + "/" + update.interim()
                + "/" + update.update() + "/" + update.patch());
        System.out.println("namedTen="
                + ten.feature() + "/" + ten.interim()
                + "/" + ten.update() + "/" + ten.patch());
        System.out.println("namedPatched="
                + patched.feature() + "/" + patched.interim()
                + "/" + patched.update() + "/" + patched.patch());
        System.out.println("fifthComponent=" + extended.version().get(4));

        System.out.println("earlyList=" + early.version());
        System.out.println("earlyPre=" + early.pre().orElse("none"));
        System.out.println("earlyBuild=" + early.build().orElse(-1));
        System.out.println("vendorList=" + vendor.version());
        System.out.println("vendorBuild=" + vendor.build().orElse(-1));
        System.out.println("vendorOptional="
                + vendor.optional().orElse("none"));
        System.out.println("sameNumericList="
                + update.version().equals(vendor.version()));
        System.out.println("wholeVersionEqual="
                + update.equals(vendor));

        boolean addBlocked = false;
        boolean setBlocked = false;
        try {
            update.version().add(99);
        } catch (UnsupportedOperationException expected) {
            addBlocked = true;
        }
        try {
            update.version().set(0, 99);
        } catch (UnsupportedOperationException expected) {
            setBlocked = true;
        }
        System.out.println("addBlocked=" + addBlocked);
        System.out.println("setBlocked=" + setBlocked);

        boolean shortIndexBlocked = false;
        try {
            ten.version().get(1);
        } catch (IndexOutOfBoundsException expected) {
            shortIndexBlocked = true;
        }
        System.out.println("shortIndexBlocked=" + shortIndexBlocked);
        System.out.println("internalZerosAllowed="
                + patched.version().equals(List.of(21, 0, 0, 1)));

        String[] invalid = {"21.0", "17.0.0", "01", "21..1", "21.0.01"};
        int invalidCount = 0;
        for (var text : invalid) {
            if (rejects(text)) {
                invalidCount++;
            }
        }
        System.out.println("invalidCount=" + invalidCount);
        System.out.println("numericOrdering="
                + (parse("21.0.9").compareTo(parse("21.0.10")) < 0));
        System.out.println("earlyBeforeGA="
                + (early.compareTo(parse("21")) < 0));

        var baseBuild = parse("21.0.1+12");
        System.out.println("optionalAffectsCompare="
                + (baseBuild.compareTo(vendor) < 0));
        System.out.println("ignoreOptionalCompare="
                + (baseBuild.compareToIgnoreOptional(vendor) == 0));
        System.out.println("ignoreOptionalEquals="
                + baseBuild.equalsIgnoreOptional(vendor));

        System.out.println("featureThresholdTrue="
                + (parse("17.0.12").feature() >= 17));
        System.out.println("featureThresholdFalse="
                + (parse("11").feature() >= 17));
        var running = Runtime.version();
        System.out.println("runtimeNonEmpty="
                + !running.version().isEmpty());
        System.out.println("runtimeFirstEqualsFeature="
                + (running.version().get(0) == running.feature()));
        System.out.println("vendorText=" + vendor.toString());
    }
}
```

Lệnh biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 RuntimeVersionComponentsDemo.java
java RuntimeVersionComponentsDemo
```

**Stdout chính xác:**

```text
tenList=[10]
updateList=[21, 0, 1]
patchedList=[21, 0, 0, 1]
extendedList=[21, 0, 1, 2, 3]
updateListSize=3
firstComponent=21
namedUpdate=21/0/1/0
namedTen=10/0/0/0
namedPatched=21/0/0/1
fifthComponent=3
earlyList=[21]
earlyPre=ea
earlyBuild=7
vendorList=[21, 0, 1]
vendorBuild=12
vendorOptional=LTS
sameNumericList=true
wholeVersionEqual=false
addBlocked=true
setBlocked=true
shortIndexBlocked=true
internalZerosAllowed=true
invalidCount=5
numericOrdering=true
earlyBeforeGA=true
optionalAffectsCompare=true
ignoreOptionalCompare=true
ignoreOptionalEquals=true
featureThresholdTrue=true
featureThresholdFalse=false
runtimeNonEmpty=true
runtimeFirstEqualsFeature=true
vendorText=21.0.1+12-LTS
```

### Phân tích các nhóm kết quả của chương trình

**Nhóm 1 — danh sách số và vị trí:**

- `tenList=[10]`: chỉ một thành phần số.
- `updateList=[21, 0, 1]`: có ba thành phần, không tự chèn `0` ở cuối.
- `patchedList=[21, 0, 0, 1]`: hai số 0 ở giữa vẫn được giữ.
- `extendedList=[21, 0, 1, 2, 3]`: có thành phần thứ năm, nên `fifthComponent=3`.
- `namedUpdate=21/0/1/0` và `namedTen=10/0/0/0`: các accessor có tên trả 0 khi thành phần tương ứng thiếu.

**Nhóm 2 — khác biệt giữa số và metadata:**

- `earlyList=[21]`, `earlyPre=ea`, `earlyBuild=7`: pre-release và build không đi vào danh sách số.
- `vendorList=[21, 0, 1]`, `vendorBuild=12`, `vendorOptional=LTS`: cả build 12 và LTS nằm ngoài list.
- `sameNumericList=true` nhưng `wholeVersionEqual=false`: cùng dãy số **không** có nghĩa cùng toàn bộ version string.

**Nhóm 3 — tính bất biến và index:**

- `addBlocked=true` và `setBlocked=true`: danh sách của `version()` không được sửa qua API `List`.
- `shortIndexBlocked=true`: `get(1)` trên phiên bản chỉ có `[10]` không hợp lệ.
- `internalZerosAllowed=true`: `21.0.0.1` vẫn là version number hợp lệ.

**Nhóm 4 — tính hợp lệ và so sánh:**

- `invalidCount=5` xác nhận năm chuỗi bị từ chối theo quy tắc không có trailing zero/leading zero và cú pháp dấu chấm hợp lệ.
- `numericOrdering=true`: `21.0.9` nhỏ hơn `21.0.10` theo số nguyên.
- `earlyBeforeGA=true`: `21-ea+7` được xếp trước `21` dù đều có `version() = [21]`.
- `optionalAffectsCompare=true`, `ignoreOptionalCompare=true`, `ignoreOptionalEquals=true`: chỉ phép so sánh được yêu cầu mới bỏ qua metadata optional.

**Nhóm 5 — check feature và quan sát runtime:**

- `featureThresholdTrue=true` ở `17.0.12` và `featureThresholdFalse=false` ở `11` minh họa điều kiện feature tối thiểu.
- `runtimeNonEmpty=true` và `runtimeFirstEqualsFeature=true` dựa trên invariant của API, không đoán version hiện tại là bao nhiêu.
- `vendorText=21.0.1+12-LTS` cho thấy `toString()` biểu diễn lại **toàn bộ version string**, không chỉ các số.

Chương trình không phụ thuộc thời gian, hệ điều hành, quốc gia, nội dung file hay version của JVM dùng để chạy, ngoài việc cần Java 17+ để biên dịch các cú pháp trong ví dụ.

## 17. Những lỗi thường gặp và cách sửa

### Lỗi A: Nghĩ `version()` luôn có bốn phần tử

```java
var v = Runtime.Version.parse("21");
int patch = v.version().get(3); // IndexOutOfBoundsException
```

**Sửa:** `v.patch()` nếu cần giá trị patch mặc định 0, hoặc kiểm `size()` trước khi đọc index.

### Lỗi B: Tự thêm số 0 vào danh sách rồi gọi là version number gốc

`[21, 0, 1]` khác `[21, 0, 1, 0]` về độ dài. `"21.0.1.0"` còn **không hợp lệ** theo ngữ pháp vì trailing zero.

**Sửa:** giữ nguyên list gốc; nếu schema nội bộ cần bốn số, tạo representation mới từ các accessor và ghi rõ đó là dữ liệu normalized.

### Lỗi C: Nhầm số build là phần tử thứ tư

`21.0.1+12` có `version()=[21,0,1]` và `build()=12`, **không** có `patch()=12`.

**Sửa:** đọc `build()` riêng qua `Optional<Integer>`.

### Lỗi D: Nghĩ `21-ea+7` chứa hai số phiên bản `21` và `7`

`7` là build number, không phải thành phần VNUM. **Sửa:** phân biệt `version()` và `build()`.

### Lỗi E: Sửa list để thay phiên bản Java hiện tại

`Runtime.Version.version()` trả list unmodifiable; `add`/`set`/`remove` không được hỗ trợ.

**Sửa:** coi `Runtime.Version` là giá trị mô tả. Nếu cần danh sách mutable tạm, copy bằng `new ArrayList<>(v.version())`; không dùng bản copy để tưởng đã sửa Runtime.

### Lỗi F: So sánh chuỗi `"21.0.9"` và `"21.0.10"` theo thứ tự chữ

So sánh lexicographic có thể sai về số. **Sửa:** dùng `Runtime.Version.compareTo`, không dùng `String.compareTo`.

### Lỗi G: So `version()` bằng nhau rồi khẳng định hai bản JDK giống hệt

`21-ea+7` và `21` có list số giống nhau nhưng trạng thái pre-release khác.

**Sửa:** dùng `Runtime.Version.equals` hoặc `compareTo` khi cần xét version string đầy đủ.

### Lỗi H: Nhầm `compareToIgnoreOptional` với việc bỏ mọi hậu tố

Method này chỉ bỏ **optional build information**, không bỏ `pre`, `build` hoặc số thành phần.

**Sửa:** đọc đúng hợp đồng và dùng `equalsIgnoreOptional` tương ứng.

### Lỗi I: Gọi `get(4)` rồi suy luận luôn là số bản vá

Vị trí 5 trở đi dành cho downstream implementors, không có một ngữ nghĩa ứng dụng phổ quát.

**Sửa:** chỉ diễn giải theo tài liệu của bản phân phối cụ thể.

### Lỗi J: Đọc `Runtime.version()` rồi assert một JDK cố định trong unit test

Khi chạy trên JDK khác, test sẽ fail dù logic đúng. **Sửa:** `Runtime.Version.parse("21.0.1")` cho test deterministic; `Runtime.version()` cho integration/environment telemetry.

### Lỗi K: Dùng tên accessor cũ với ngữ nghĩa cũ

`major()/minor()/security()` là các accessor legacy đã deprecated sau JEP 322; không dùng trong code mới.

**Sửa:** `feature()/interim()/update()/patch()`.

### Lỗi L: Cho rằng `feature() >= 17` chứng minh toàn bộ ứng dụng tương thích

Điều kiện feature không kiểm compile target, class loading, API thực tế, dependency hay trạng thái cập nhật bảo mật.

**Sửa:** kết hợp `--release`, toolchain, integration tests và chính sách dependency/runtime.

### Lỗi M: Dùng `Runtime.Version` để parse mọi phiên bản phần mềm

Đặc tả Java version string không nhất thiết tương thích với SemVer hoặc format riêng của thư viện.

**Sửa:** dùng parser theo đặc tả của từng domain.

### Lỗi N: Không xử lý input version không hợp lệ

`Runtime.Version.parse("21.0")` ném `IllegalArgumentException`, không tự xóa số 0 cuối để giúp bạn.

**Sửa:** kiểm đầu vào và xử lý lỗi parse rõ ràng. Đừng sửa string âm thầm nếu một mã version sai là lỗi cần báo.

## 18. Checklist đọc danh sách thành phần số trong sản phẩm thực

1. **Nguồn dữ liệu là version Java hay version thư viện khác?** Dùng đúng parser.
2. **Bạn cần bản Java đang chạy hay một chuỗi giả định?** `Runtime.version()` vs `Runtime.Version.parse`.
3. **Đã phân biệt `$VNUM` với `pre/build/optional` chưa?**
4. **Có giả định cố định bốn số không?** `version().size()` có thể khác 4.
5. **Có dùng `get(0)` đúng và kiểm index 1+ không?**
6. **Có nhớ rằng phiên bản không có patch được accessor trả 0 nhưng list không chứa phần tử patch không?**
7. **Có giữ zero trung gian khi cần ghi lại số version không?**
8. **Có tránh tự thêm trailing zero vào version string không?**
9. **Có dùng `feature()/interim()/update()/patch()` thay cho accessor deprecated không?**
10. **Có cho phép thành phần thứ năm theo vendor policy không?**
11. **Có tránh sửa list unmodifiable không?**
12. **Có so sánh số bằng `compareTo` thay vì so chuỗi không?**
13. **Có xét pre-release trong điều kiện tương thích không?**
14. **Có biết chính xác lúc nào bỏ optional build info khi so không?**
15. **Có dùng `Runtime.Version.equals` khi cần full identity không?**
16. **Có dùng `Runtime.version()` cho dữ liệu quan sát, không hardcode test kỳ vọng version máy không?**
17. **Có kiểm parse lỗi và giới hạn kích thước input từ nguồn không tin cậy không?**
18. **Có tách feature number khỏi tuyên bố security/LTS/compatibility không?**
19. **Có trình bày chính xác metadata version build của bản phân phối không?**
20. **Có test các trường hợp ngắn, update, patch, pre-release, build, optional, extra và invalid không?**

## 19. Bài tập và đáp án

**Câu 1.** `Runtime.Version.parse("21.0.1").version()` trả danh sách nào?

**Câu 2.** Danh sách `version()` có kiểu Java nào và có được gọi `set(0, ...)` không?

**Câu 3.** `Runtime.Version.parse("10").version()` có bao nhiêu phần tử? `patch()` bằng bao nhiêu?

**Câu 4.** Vì sao `Runtime.Version.parse("17.0.0")` không hợp lệ trong khi `Runtime.Version.parse("21.0.0.1")` hợp lệ?

**Câu 5.** `21.0.1.2.3` có bao nhiêu thành phần? `patch()` lấy số nào?

**Câu 6.** Với `21-ea+7`, `version()`, `pre()`, `build()` có ý nghĩa gì?

**Câu 7.** `21.0.1+12-LTS` có đưa `12` vào list số không?

**Câu 8.** Nếu chỉ cần số Java feature tối thiểu, chọn `version().get(0)` hay `feature()`?

**Câu 9.** Nếu cần thứ tự giữa `21.0.9` và `21.0.10`, nên dùng `String.compareTo` hay `Runtime.Version.compareTo`?

**Câu 10.** Hai bản `21-ea+7` và `21` có cùng `version()` không? Có tương đương toàn bộ version không?

**Câu 11.** `compareToIgnoreOptional` có bỏ pre-release và build number không?

**Câu 12.** `Runtime.version()` có luôn trả `[17]` nếu class được biên dịch bằng `--release 17` không?

**Câu 13.** `feature() >= 21` có bảo đảm mọi API và dependency trong chương trình đều tương thích không?

**Câu 14.** Vì sao không nên dùng `Runtime.Version` làm parser SemVer cho mọi thư viện?

**Câu 15.** Cho `Runtime.Version.parse("21.0.1")`, gọi `version().get(3)` và `patch()` cho kết quả gì?

**Câu 16.** `equalsIgnoreOptional` và `equals` có thể khác nhau trong trường hợp nào?

**Câu 17.** Phần tử thứ năm của `21.0.1.2.3` có ý nghĩa cố định trong mọi JDK không?

**Câu 18.** Khi test tính đúng đắn của `version()`, nên dựa vào chuỗi tự parse hay giá trị JVM thật?

**Đáp án:**

1. `[21, 0, 1]`.
2. `List<Integer>` không sửa được; `set` gây `UnsupportedOperationException`.
3. Một phần tử `[10]`; `patch()==0` vì thành phần patch vắng mặt.
4. Số 0 **cuối** bị cấm; số 0 **ở giữa** được phép khi sau đó có phần tử khác 0.
5. Năm phần tử; `patch() == 2`, còn số `3` là phần tử thứ năm.
6. `version()=[21]`, `pre()=ea`, `build()=7`; ea và 7 không thuộc VNUM.
7. Không; list là `[21,0,1]`, build là 12.
8. Cả hai cho số đầu nhưng `feature()` diễn đạt ý định rõ và không phụ thuộc index.
9. `Runtime.Version.compareTo` vì so theo số, không so ký tự.
10. Cùng danh sách `[21]` nhưng trạng thái pre-release khác; không tương đương toàn bộ.
11. Không. Chỉ bỏ optional build information.
12. Không. `Runtime.version()` phản ánh **JVM đang chạy**.
13. Không; cần kiểm thêm compile target, API, runtime, dependency và hỗ trợ.
14. Vì mỗi hệ thống có ngữ pháp và quy tắc so sánh version riêng.
15. `get(3)` ném `IndexOutOfBoundsException`; `patch()` trả `0`.
16. Khi chỉ khác optional build metadata, ví dụ `21.0.1+12` và `21.0.1+12-LTS`.
17. Không; các vị trí từ thứ năm được để cho downstream implementation.
18. Dùng `Runtime.Version.parse` trên chuỗi cố định để test deterministic; dùng `Runtime.version()` cho integration observation.

## 20. Tổng kết và nguồn chính thức (kiến thức còn áp dụng)

- `Runtime.Version.version()` trả **`List<Integer>` unmodifiable**, luôn có tối thiểu một phần tử.
- List chỉ chứa các số trong **`$VNUM`**; **không** chứa `pre`, `build` hay `optional`.
- Bốn vị trí chuẩn là **`FEATURE.INTERIM.UPDATE.PATCH`**; dùng accessor có tên `feature()/interim()/update()/patch()`.
- Version number **không có trailing zero**. Zero ở giữa vẫn hợp lệ. List không tự đệm đủ bốn vị trí.
- Thành phần thứ năm trở đi có thể do downstream implementors quy định; không gán ý nghĩa phổ quát.
- `version()` không sửa được. Nếu cần danh sách mutable của riêng ứng dụng, tạo bản copy.
- `Runtime.Version.compareTo` so thành phần số và metadata theo hợp đồng; không thay bằng so sánh chuỗi.
- `Runtime.version()` lấy phiên bản JVM đang chạy; `Runtime.Version.parse` thích hợp cho test có input cố định.
- `Runtime.Version` có từ Java 9, cách đặt tên các thành phần theo JEP 322 được áp dụng từ Java 10 và vẫn hiện hành. Không dùng accessor cũ đã deprecated.
- Version number không tự cung cấp tình trạng vá bảo mật, chính sách LTS hoặc bảo đảm tương thích của ứng dụng.

Nguồn chính thức:

1. [Java SE 26 — `Runtime.Version`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Runtime.Version.html): `version()`, `parse`, bốn accessor số, `pre/build/optional`, so sánh và tính unmodifiable.
2. [Java SE 26 — `Runtime.version()`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Runtime.html#version()): đọc phiên bản của JVM đang chạy.
3. [Oracle Java SE 26 — Version-String Format](https://docs.oracle.com/en/java/javase/26/install/version-string-format.html): cấu trúc `$FEATURE.$INTERIM.$UPDATE.$PATCH` và quy tắc không có trailing zero.
4. [JEP 322 — Time-Based Release Versioning](https://cr.openjdk.org/~mr/jdk/jeps/322-time-based-release-versioning.html): mô hình số version theo chu kỳ phát hành, accessor có tên và vị trí dành cho downstream implementors.
5. [Java SE 26 — `List`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/List.html): cách truy cập bằng index và `UnsupportedOperationException` khi thao tác sửa trên list unmodifiable.
