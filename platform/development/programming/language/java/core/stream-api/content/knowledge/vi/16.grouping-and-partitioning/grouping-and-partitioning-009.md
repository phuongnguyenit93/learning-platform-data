# Giữ thứ tự nhóm và thứ tự phần tử trong từng nhóm

## 1. Hai loại thứ tự cần kiểm soát

Khi xử lý dữ liệu bằng **Java Stream API** (`JAVA_STREAM_API`), một pipeline có thể lấy nguồn từ `List`, lọc và biến đổi bằng `filter` / `map`, rồi kết thúc bằng `collect(Collectors.groupingBy(...))`. Kết quả là một `Map` chứa nhiều nhóm. Tuy nhiên, câu hỏi "**kết quả có giữ thứ tự không?**" thực ra phải tách thành **hai câu hỏi khác nhau**:

1. **Thứ tự các nhóm (thứ tự khóa `Map`):** khi duyệt `map.keySet()` hoặc `map.entrySet()`, nhóm nào xuất hiện trước?
2. **Thứ tự phần tử bên trong mỗi nhóm:** với một khóa cụ thể, các bản ghi trong `List` / `Set` có được duyệt theo thứ tự gặp của nguồn không?

Hai tầng thứ tự do **hai lựa chọn độc lập** điều khiển:

- `mapFactory` quyết định loại `Map` và cách duyệt **khóa nhóm**.
- `downstream collector` quyết định loại collection và cách duyệt **phần tử trong nhóm**.

Nếu nghiệp vụ yêu cầu "nhóm xuất hiện theo thứ tự lần đầu gặp, mỗi nhóm giữ nguyên trình tự đơn hàng", ta thường chọn:

```java
Collectors.groupingBy(
    DonHang::getDanhMuc,
    LinkedHashMap::new,
    Collectors.toCollection(ArrayList::new)
)
```

Bài thuộc chương **Phân nhóm và phân hoạch**. Sau bài này, bạn có thể:

- Phân biệt *encounter order*, thứ tự chèn của `LinkedHashMap` và thứ tự phần tử của `ArrayList` / `LinkedHashSet`.
- Dùng overload ba tham số của `Collectors.groupingBy` để kiểm soát hai tầng thứ tự.
- Sắp xếp khóa hoặc phần tử trong từng nhóm mà không vô tình thay đổi tầng thứ tự còn lại.
- Dự đoán điều gì xảy ra với nguồn không có thứ tự, `unordered()` hoặc `parallelStream()`.
- Thiết kế kiểm thử độc lập cho cả thứ tự khóa, thứ tự phần tử và quy tắc loại trùng.

## 2. Encounter order: thứ tự gặp của stream

**Encounter order** là thứ tự gặp phần tử mà nguồn stream và các thao tác trung gian cam kết, nếu có. Ví dụ:

```java
List<String> ma = Arrays.asList(
    "DH01", "DH02", "DH03", "DH04"
);

ma.stream(); // Encounter order: DH01, DH02, DH03, DH04
```

Một số nguồn có hoặc không có thứ tự gặp được bảo đảm:

| Nguồn | Encounter order được bảo đảm? | Ghi chú |
| --- | --- | --- |
| `ArrayList.stream()` | Có | Theo thứ tự chỉ số. |
| `LinkedHashSet.stream()` | Có | Theo thứ tự chèn phần tử. |
| `Arrays.stream(array)` | Có | Theo thứ tự chỉ số mảng. |
| `IntStream.range(0, 10)` | Có | Theo thứ tự số tăng dần. |
| `HashSet.stream()` | Không | Thứ tự lặp của `HashSet` không phải hợp đồng. |
| `HashMap.entrySet().stream()` | Không | Không nên xem thứ tự duyệt của `HashMap` là cố định. |

Một số thao tác trung gian cũng có thể ảnh hưởng đến thứ tự:

- `filter` giữ thứ tự tương đối của phần tử còn lại trên ordered stream.
- `map` biến đổi giá trị nhưng giữ quan hệ thứ tự tương ứng trên ordered stream.
- `sorted` thiết lập thứ tự sắp xếp mới.
- `distinct` trên ordered stream giữ phần tử xuất hiện đầu tiên trong các phần tử bằng nhau.
- `unordered()` bỏ ràng buộc encounter order; không có nghĩa "đảo ngược" hay "xáo trộn chắc chắn".

`collect` là terminal operation: các bước `filter`, `map` và `sorted` ở trước có thể lazy, nhưng quá trình phân nhóm và tạo các collection kết quả được thực hiện khi `collect` tiêu thụ stream.

## 3. Chương trình hoàn chỉnh: giữ cả thứ tự nhóm và phần tử

Dùng các đơn hàng sau làm ví dụ xuyên suốt (Java 8+):

| Thứ tự đầu vào | Mã đơn | Danh mục | Khách hàng | Giá trị |
| ---: | --- | --- | --- | ---: |
| 1 | DH01 | Sách | KH-A | 120.000 |
| 2 | DH02 | Điện tử | KH-B | 900.000 |
| 3 | DH03 | Sách | KH-C | 150.000 |
| 4 | DH04 | Đồ dùng | KH-A | 80.000 |
| 5 | DH05 | Điện tử | KH-B | 700.000 |
| 6 | DH06 | Sách | KH-A | 120.000 |

Mã Java tự chứa:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class NhomDonHangCoThuTu {
    static final class DonHang {
        private final String ma;
        private final String danhMuc;
        private final String khachHang;
        private final long soTien;

        DonHang(String ma, String danhMuc, String khachHang, long soTien) {
            this.ma = ma;
            this.danhMuc = danhMuc;
            this.khachHang = khachHang;
            this.soTien = soTien;
        }

        String getMa() {
            return ma;
        }

        String getDanhMuc() {
            return danhMuc;
        }

        String getKhachHang() {
            return khachHang;
        }

        long getSoTien() {
            return soTien;
        }

        @Override
        public String toString() {
            return ma;
        }
    }

    static List<DonHang> duLieu() {
        return Arrays.asList(
            new DonHang("DH01", "Sách", "KH-A", 120_000L),
            new DonHang("DH02", "Điện tử", "KH-B", 900_000L),
            new DonHang("DH03", "Sách", "KH-C", 150_000L),
            new DonHang("DH04", "Đồ dùng", "KH-A", 80_000L),
            new DonHang("DH05", "Điện tử", "KH-B", 700_000L),
            new DonHang("DH06", "Sách", "KH-A", 120_000L)
        );
    }

    public static void main(String[] args) {
        List<DonHang> donHang = duLieu();

        LinkedHashMap<String, ArrayList<DonHang>> nhom = donHang.stream()
            .collect(Collectors.groupingBy(
                DonHang::getDanhMuc,
                LinkedHashMap::new,
                Collectors.toCollection(ArrayList::new)
            ));

        System.out.println(new ArrayList<>(nhom.keySet()));
        System.out.println(nhom.get("Sách"));
        System.out.println(nhom.get("Điện tử"));
        System.out.println(nhom.get("Đồ dùng"));
    }
}
```

Đầu ra:

```text
[Sách, Điện tử, Đồ dùng]
[DH01, DH03, DH06]
[DH02, DH05]
[DH04]
```

**Tại sao kết quả như vậy?**

1. Nguồn `donHang` là `List`, có encounter order xác định.
2. Danh mục "Sách" xuất hiện đầu tiên, "Điện tử" xuất hiện thứ hai, "Đồ dùng" xuất hiện thứ tư; `LinkedHashMap` giữ thứ tự chèn khóa theo lần xuất hiện đầu.
3. `Collectors.toCollection(ArrayList::new)` thu các đơn của mỗi danh mục vào `ArrayList`.
4. Các đơn "Sách" đi theo thứ tự gặp `DH01 → DH03 → DH06`; mỗi lần classifier cho cùng khóa, bản ghi được đưa vào nhóm tương ứng.
5. Không có bước `sorted`, `unordered` hay hành động phụ bên ngoài làm thay đổi thứ tự này.

Các ví dụ ngắn tiếp theo giả định bạn đã đặt chúng trong `main` của lớp trên, nơi có biến:

```java
List<DonHang> donHang = duLieu();
```

Các mã ví dụ sử dụng `Collectors` và các lớp đã nhập ở chương trình trên; nếu dùng đoạn riêng trong lớp khác, hãy bổ sung import tương ứng.

## 4. Overload ba tham số và hai tầng điều khiển

Chữ ký (rút gọn) của overload cần dùng:

```java
<T, K, D, A, M extends Map<K, D>> Collector<T, ?, M> groupingBy(
    Function<? super T, ? extends K> classifier,
    Supplier<M> mapFactory,
    Collector<? super T, A, D> downstream
);
```

Ý nghĩa của từng vị trí:

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| `classifier` | Tính khóa nhóm từ từng phần tử | `DonHang::getDanhMuc` |
| `mapFactory` | Tạo loại map chứa các nhóm | `LinkedHashMap::new`, `TreeMap::new` |
| `downstream` | Tích lũy những phần tử có cùng khóa | `toList()`, `toCollection(ArrayList::new)`, `counting()` |
| Giá trị trả về | Một map với giá trị từng nhóm do downstream tạo | `LinkedHashMap<String, ArrayList<DonHang>>` |

Chỉ viết:

```java
Map<String, List<DonHang>> nhom = donHang.stream()
    .collect(Collectors.groupingBy(DonHang::getDanhMuc));
```

thì **không có bảo đảm về loại map hoặc thứ tự duyệt khóa**. Dù JDK hiện tại có thể dùng `HashMap`, đó không phải hợp đồng bạn nên dựa vào.

Đồng thời, `Collectors.toList()` không cam kết kiểu list cụ thể, khả năng sửa, tính thread-safe hay serializability. Khi chỉ cần `List` giữ encounter order thì dùng `toList()` là đủ; khi thật sự cần một `ArrayList` có thể sửa, dùng `toCollection(ArrayList::new)`.

### Mẫu chọn hai tầng thứ tự

```java
// Thứ tự khóa theo lần gặp đầu tiên.
// Mỗi nhóm là một ArrayList theo encounter order.
LinkedHashMap<String, ArrayList<DonHang>> nhom = donHang.stream()
    .collect(Collectors.groupingBy(
        DonHang::getDanhMuc,
        LinkedHashMap::new,
        Collectors.toCollection(ArrayList::new)
    ));
```

Đây là mẫu phù hợp cho báo cáo muốn hiển thị các danh mục theo thứ tự xuất hiện của dữ liệu gốc, đồng thời giữ nguyên thứ tự các bản ghi bên trong mỗi danh mục.

## 5. Chỉ cần giữ thứ tự phần tử trong nhóm: `toList()`

Khi giao diện chỉ truy cập từng nhóm theo khóa và **không quan tâm thứ tự các khóa**, không nhất thiết phải chọn `LinkedHashMap`.

```java
Map<String, List<DonHang>> nhom = donHang.stream()
    .collect(Collectors.groupingBy(
        DonHang::getDanhMuc,
        Collectors.toList()
    ));

System.out.println(nhom.get("Sách")); // [DH01, DH03, DH06]
```

Trên ordered stream từ `List`, `Collectors.toList()` thu phần tử trong mỗi nhóm theo thứ tự gặp; nhưng khi in toàn bộ `nhom`, không được giả định thứ tự khóa là `[Sách, Điện tử, Đồ dùng]`.

Nếu cần kết quả list có thể sửa rõ ràng:

```java
Map<String, ArrayList<DonHang>> nhom = donHang.stream()
    .collect(Collectors.groupingBy(
        DonHang::getDanhMuc,
        Collectors.toCollection(ArrayList::new)
    ));
```

Điều này thay đổi **kiểu collection của mỗi nhóm**, không bổ sung cam kết về thứ tự duyệt khóa của map.

**Ngược lại:** chọn `LinkedHashMap::new` mà downstream là `Collectors.toSet()` chỉ xác định thứ tự khóa, **không đảm bảo thứ tự phần tử của set**.

## 6. Giữ thứ tự gặp nhưng loại trùng với `LinkedHashSet`

Có những yêu cầu không muốn giữ toàn bộ phần tử: "Mỗi danh mục có những **khách hàng duy nhất** nào, theo thứ tự xuất hiện đầu tiên?". Lúc này downstream nên dùng `LinkedHashSet`.

```java
import java.util.LinkedHashSet;

LinkedHashMap<String, LinkedHashSet<String>> khachTheoDanhMuc =
    donHang.stream()
        .collect(Collectors.groupingBy(
            DonHang::getDanhMuc,
            LinkedHashMap::new,
            Collectors.mapping(
                DonHang::getKhachHang,
                Collectors.toCollection(LinkedHashSet::new)
            )
        ));

System.out.println(new ArrayList<>(khachTheoDanhMuc.keySet()));
// [Sách, Điện tử, Đồ dùng]

System.out.println(khachTheoDanhMuc.get("Sách"));
// [KH-A, KH-C]

System.out.println(khachTheoDanhMuc.get("Điện tử"));
// [KH-B]
```

Ý nghĩa:

- `LinkedHashMap` giữ **thứ tự xuất hiện đầu tiên của các danh mục**.
- `mapping(DonHang::getKhachHang, ...)` chỉ lấy mã khách hàng của từng đơn.
- `LinkedHashSet` giữ **mã khách hàng duy nhất**, theo thứ tự chèn lần đầu trong nhóm.
- Ở nhóm "Sách", `KH-A` xuất hiện lần đầu ở `DH01`, `KH-C` ở `DH03`, còn `KH-A` ở `DH06` bị loại trùng.

Khác biệt giữa list và set:

| Downstream | Có giữ phần tử trùng? | Thứ tự duyệt phần tử |
| --- | --- | --- |
| `toList()` | Có | Theo encounter order trên ordered stream |
| `toCollection(ArrayList::new)` | Có | Theo encounter order trên ordered stream |
| `toSet()` | Không | Không cam kết |
| `toCollection(LinkedHashSet::new)` | Không | Theo thứ tự chèn các giá trị duy nhất |
| `toCollection(TreeSet::new)` | Không | Theo thứ tự sắp xếp của `TreeSet`, không phải thứ tự gặp |

`LinkedHashSet` xác định hai phần tử trùng nhau theo `equals`/`hashCode`. Nếu khóa nhận diện khách hàng là đối tượng tùy chỉnh, hãy triển khai hợp đồng hai phương thức đó nhất quán và tránh thay đổi khóa sau khi đã đưa vào set.

## 7. Sắp xếp nhóm theo khóa bằng `TreeMap`

`LinkedHashMap` lưu thứ tự **gặp trước**, không sắp xếp alphabet. Khi muốn thứ tự khóa theo tiêu chí so sánh, dùng một map có thứ tự sắp xếp.

```java
import java.util.TreeMap;

TreeMap<String, List<DonHang>> nhomTheoKhoa = donHang.stream()
    .collect(Collectors.groupingBy(
        DonHang::getDanhMuc,
        TreeMap::new,
        Collectors.toList()
    ));

System.out.println(nhomTheoKhoa.keySet());
```

`TreeMap` với constructor không tham số dùng thứ tự tự nhiên của `String`, tức so sánh chuỗi Java theo mã ký tự; **không phải sắp xếp tiếng Việt theo quy tắc từ điển**. Nếu muốn thứ tự theo ngôn ngữ hoặc nghiệp vụ, cần cung cấp comparator phù hợp.

### Ví dụ thứ tự khóa được định nghĩa bởi nghiệp vụ

Giả sử giao diện muốn hiển thị lần lượt "Điện tử", "Sách", rồi "Đồ dùng", bất kể thứ tự gặp:

```java
import java.util.Comparator;
import java.util.HashMap;
import java.util.TreeMap;

Map<String, Integer> thuTu = new HashMap<>();
thuTu.put("Điện tử", 0);
thuTu.put("Sách", 1);
thuTu.put("Đồ dùng", 2);

Comparator<String> thuTuNghiepVu =
    Comparator.comparingInt(thuTu::get);

TreeMap<String, List<DonHang>> nhom = donHang.stream()
    .collect(Collectors.groupingBy(
        DonHang::getDanhMuc,
        () -> new TreeMap<>(thuTuNghiepVu),
        Collectors.toList()
    ));

System.out.println(new ArrayList<>(nhom.keySet()));
// [Điện tử, Sách, Đồ dùng]
```

Ví dụ này giả định **mọi khóa đều tồn tại trong `thuTu` và thứ hạng không trùng nhau**. Với dữ liệu thực tế, comparator dùng làm tiêu chí xác định khóa của `TreeMap`: nếu hai khóa khác nhau nhưng comparator trả `0`, chúng có thể bị coi là cùng khóa. Vì vậy comparator phải nhất quán với tiêu chí phân biệt nhóm, đồng thời có phương án cho khóa lạ hoặc danh mục chưa xác định.

Cách khác là phân nhóm trước, rồi đưa danh sách các nhóm vào thứ tự hiển thị theo danh sách danh mục chuẩn của nghiệp vụ. Giải pháp này thường dễ kiểm soát hơn khi quy tắc hiển thị thay đổi.

## 8. Sắp xếp phần tử trong từng nhóm mà không đổi thứ tự nhóm

Một sai lầm phổ biến là sắp xếp **toàn bộ stream trước khi phân nhóm** khi thực ra chỉ muốn sắp xếp phần tử **bên trong mỗi nhóm**. Việc sắp xếp trước có thể làm thay đổi cả thứ tự xuất hiện đầu của khóa nhóm.

### 8.1. Sắp xếp trước khi `groupingBy`: thay đổi cả hai tầng

```java
import java.util.Comparator;

LinkedHashMap<String, List<DonHang>> theoGiaTri = donHang.stream()
    .sorted(Comparator.comparingLong(DonHang::getSoTien))
    .collect(Collectors.groupingBy(
        DonHang::getDanhMuc,
        LinkedHashMap::new,
        Collectors.toList()
    ));

System.out.println(new ArrayList<>(theoGiaTri.keySet()));
// [Đồ dùng, Sách, Điện tử]

System.out.println(theoGiaTri.get("Sách"));
// [DH01, DH06, DH03]

System.out.println(theoGiaTri.get("Điện tử"));
// [DH05, DH02]
```

Lý do:

1. `DH04` có giá trị 80.000 nên xuất hiện đầu sau `sorted`; khóa "Đồ dùng" được chèn trước.
2. `DH01` và `DH06` cùng giá trị 120.000; với nguồn ordered, `sorted` ổn định, giữ thứ tự tương đối của hai phần tử có khóa so sánh bằng nhau.
3. Tiếp theo mới có nhóm "Điện tử" ở mức 700.000 và 900.000.

**Kết luận:** `sorted` ở trước `groupingBy` làm thay đổi encounter order mà map dùng để quyết định vị trí chèn khóa.

### 8.2. Chỉ sắp xếp list sau khi đã phân nhóm

Nếu muốn **giữ thứ tự nhóm ban đầu** là [Sách, Điện tử, Đồ dùng], nhưng mỗi nhóm sắp xếp theo giá tăng dần, có thể dùng downstream `collectingAndThen`:

```java
import java.util.Comparator;

LinkedHashMap<String, ArrayList<DonHang>> nhom = donHang.stream()
    .collect(Collectors.groupingBy(
        DonHang::getDanhMuc,
        LinkedHashMap::new,
        Collectors.collectingAndThen(
            Collectors.toCollection(ArrayList::new),
            list -> {
                list.sort(Comparator.comparingLong(DonHang::getSoTien));
                return list;
            }
        )
    ));

System.out.println(new ArrayList<>(nhom.keySet()));
// [Sách, Điện tử, Đồ dùng]

System.out.println(nhom.get("Sách"));
// [DH01, DH06, DH03]

System.out.println(nhom.get("Điện tử"));
// [DH05, DH02]
```

Ở đây, collector đầu tiên thu phần tử vào từng `ArrayList`, còn hàm finisher sắp xếp **mỗi list**. Không sắp xếp stream gốc nên thứ tự chèn khóa của `LinkedHashMap` vẫn dựa trên encounter order ban đầu.

Ta dùng `toCollection(ArrayList::new)` thay vì giả định list của `Collectors.toList()` luôn có thể sửa; API `toList()` không cam kết mutability.

**Khi có nhiều phần tử bằng nhau theo comparator:** `List.sort` là stable sort, nhưng để thứ tự kết quả không phụ thuộc vào việc so sánh bằng nhau giữa những bản ghi khác nhau, có thể thêm tiêu chí phụ:

```java
Comparator<DonHang> theoGiaRoiMa =
    Comparator.comparingLong(DonHang::getSoTien)
        .thenComparing(DonHang::getMa);
```

Dùng comparator nhiều tiêu chí còn giúp kết quả dễ kiểm thử hơn khi dữ liệu được lấy từ nhiều nguồn.

## 9. Nguồn không có thứ tự: collector không thể tạo ra lịch sử không tồn tại

`LinkedHashMap` chỉ giữ **thứ tự các khóa khi chúng được đưa vào map**. Nó không thể tự suy luận được thứ tự ban đầu khi nguồn không có encounter order.

Ví dụ nguồn là `HashSet`:

```java
import java.util.HashSet;

HashSet<String> danhMuc = new HashSet<>(
    Arrays.asList("Sách", "Điện tử", "Đồ dùng")
);

LinkedHashMap<String, List<String>> nhom = danhMuc.stream()
    .collect(Collectors.groupingBy(
        s -> s.substring(0, 1),
        LinkedHashMap::new,
        Collectors.toList()
    ));
```

Thứ tự các phần tử mà `HashSet.stream()` cung cấp không được bảo đảm, nên không nên suy ra một thứ tự khóa có ý nghĩa chỉ từ `LinkedHashMap`.

Nếu cần kết quả xác định, **thiết lập thứ tự trước khi phân nhóm**:

```java
LinkedHashMap<String, List<String>> nhom = danhMuc.stream()
    .sorted()
    .collect(Collectors.groupingBy(
        s -> s.substring(0, 1),
        LinkedHashMap::new,
        Collectors.toList()
    ));
```

`sorted` tạo encounter order theo so sánh tự nhiên của `String`. Nếu muốn thứ tự nghiệp vụ cụ thể, dùng comparator thích hợp thay vì dựa vào thứ tự mặc định của bộ sưu tập.

### `unordered()` không bảo đảm thứ tự

```java
LinkedHashMap<String, List<DonHang>> nhom = donHang.stream()
    .unordered()
    .collect(Collectors.groupingBy(
        DonHang::getDanhMuc,
        LinkedHashMap::new,
        Collectors.toList()
    ));
```

`unordered()` cho phép bỏ yêu cầu bảo toàn encounter order. Kết quả có thể **trông giống thứ tự ban đầu trong một lần chạy**, nhưng đó không phải điều kiện đúng/sai mà ứng dụng được phép phụ thuộc. Nếu thứ tự xuất hiện đầu có ý nghĩa, không gọi `unordered()`.

## 10. Parallel stream: thứ tự kết quả khác thứ tự thực thi

Một stream có thứ tự vẫn giữ encounter order dù được đặt ở chế độ song song. `groupingBy` thông thường là collector **không concurrent**, hỗ trợ tổng hợp bằng những vùng tích lũy cục bộ và ghép kết quả. Vì vậy, với nguồn ordered và downstream có ngữ nghĩa giữ thứ tự, bạn có thể thu kết quả theo thứ tự gặp.

```java
LinkedHashMap<String, ArrayList<DonHang>> nhom = donHang.parallelStream()
    .collect(Collectors.groupingBy(
        DonHang::getDanhMuc,
        LinkedHashMap::new,
        Collectors.toCollection(ArrayList::new)
    ));

System.out.println(new ArrayList<>(nhom.keySet()));
// [Sách, Điện tử, Đồ dùng]

System.out.println(nhom.get("Sách"));
// [DH01, DH03, DH06]
```

Tuy nhiên, có **ba thứ tự khác nhau** cần phân biệt:

1. **Encounter order:** do nguồn và pipeline ordered xác định.
2. **Thứ tự thực thi:** thứ tự các thread gọi `classifier`, `map` hoặc các bước trung gian; **không được cam kết** trong parallel stream.
3. **Thứ tự duyệt kết quả:** do ordered stream, collector, loại map và downstream collection quyết định.

Không dùng việc nhìn log từ `peek` hoặc `map` để suy ra encounter order, vì các callback có thể được thực thi ở các thread khác nhau hoặc trong thứ tự không trực quan. Nếu đòi hỏi tuyệt đối về thứ tự chèn khóa theo quy trình nghiệp vụ, pipeline tuần tự thường dễ phân tích và kiểm soát hơn.

### 10.1. Tại sao không tự thêm vào map chung bằng `forEach`?

Ví dụ chống chỉ định:

```java
import java.util.HashMap;

Map<String, List<DonHang>> nhom = new HashMap<>();

// SAI: thay đổi HashMap và ArrayList dùng chung từ nhiều thread.
// Không dùng cách này trong ứng dụng.
donHang.parallelStream().forEach(d ->
    nhom.computeIfAbsent(
        d.getDanhMuc(),
        k -> new ArrayList<>()
    ).add(d)
);
```

`HashMap`, `ArrayList` và `LinkedHashMap` không bảo đảm an toàn cho việc sửa đồng thời. Cách trên có thể gây mất bản ghi, sai nhóm, sai thứ tự hoặc lỗi lúc chạy. Hãy dùng `collect(groupingBy(...))` để Stream API quản lý vùng tích lũy.

Ngay cả khi tự đồng bộ hóa map, `parallelStream().forEach(...)` vẫn **không cam kết encounter order** cho các lần cập nhật. Đồng bộ hóa chống race không tự khôi phục thứ tự nghiệp vụ.

### 10.2. `groupingByConcurrent` không dành cho yêu cầu thứ tự

`Collectors.groupingByConcurrent` tạo collector có đặc tính **concurrent** và **unordered**, thuận tiện trong một số bài toán tổng hợp song song nhưng **không giữ yêu cầu thứ tự phần tử của mỗi nhóm**.

```java
import java.util.concurrent.ConcurrentMap;

ConcurrentMap<String, List<DonHang>> nhomConcurrent =
    donHang.parallelStream()
        .collect(Collectors.groupingByConcurrent(
            DonHang::getDanhMuc
        ));
```

Danh sách trong từng nhóm có thể không theo thứ tự `DH01 → DH03 → DH06`. `ConcurrentMap` kết quả cũng không tự cung cấp thứ tự khóa kiểu `LinkedHashMap`.

Đừng nhầm **an toàn để collector tích lũy đồng thời** với **các list giá trị bên trong luôn thread-safe để sửa sau này**. Nếu cần cả xử lý song song và thứ tự kết quả xác định, ưu tiên collector có ngữ nghĩa ordered hoặc sắp xếp rõ ràng sau khi thu thập, và đo hiệu năng trên dữ liệu thật.

## 11. Dùng `groupingBy` với `mapping`, `filtering` và các downstream khác

### 11.1. Ánh xạ giá trị trước khi thu mỗi nhóm

Từ `List<DonHang>`, lấy các mã đơn nhưng vẫn giữ thứ tự nhóm và phần tử:

```java
LinkedHashMap<String, List<String>> maTheoDanhMuc =
    donHang.stream().collect(
        Collectors.groupingBy(
            DonHang::getDanhMuc,
            LinkedHashMap::new,
            Collectors.mapping(
                DonHang::getMa,
                Collectors.toList()
            )
        )
    );

System.out.println(maTheoDanhMuc.get("Sách"));
// [DH01, DH03, DH06]
```

`mapping` thay đổi **giá trị thu vào mỗi nhóm**, không làm thay đổi khóa của nhóm. Nếu cần mã không trùng và giữ lần xuất hiện đầu, thay `toList()` bằng `toCollection(LinkedHashSet::new)`.

### 11.2. Lọc trước hay lọc bên trong nhóm?

Khi đặt `filter` **trước** `groupingBy`, nhóm không còn phần tử có thể **không xuất hiện**:

```java
LinkedHashMap<String, List<DonHang>> trenMotTram =
    donHang.stream()
        .filter(d -> d.getSoTien() >= 100_000L)
        .collect(Collectors.groupingBy(
            DonHang::getDanhMuc,
            LinkedHashMap::new,
            Collectors.toList()
        ));

System.out.println(new ArrayList<>(trenMotTram.keySet()));
// [Sách, Điện tử] — Đồ dùng không có bản ghi đạt điều kiện.
```

Từ **Java 9**, `Collectors.filtering` cho phép lọc **bên trong mỗi nhóm**. Các nhóm vẫn có thể xuất hiện với downstream rỗng nếu phần tử được classifier phân vào nhóm nhưng không vượt điều kiện lọc:

```java
LinkedHashMap<String, List<DonHang>> trenMotTram =
    donHang.stream().collect(
        Collectors.groupingBy(
            DonHang::getDanhMuc,
            LinkedHashMap::new,
            Collectors.filtering(
                d -> d.getSoTien() >= 100_000L,
                Collectors.toList()
            )
        )
    );

System.out.println(new ArrayList<>(trenMotTram.keySet()));
// [Sách, Điện tử, Đồ dùng]

System.out.println(trenMotTram.get("Đồ dùng"));
// []
```

Khác biệt này liên quan trực tiếp đến **thứ tự khóa**: với `filter` trước, nhóm "Đồ dùng" biến mất; với downstream `filtering`, nó vẫn có vị trí trong `LinkedHashMap`. Với Java 8, nếu cần giữ đầy đủ nhóm nhưng lọc dữ liệu trong nhóm, có thể dùng một downstream collector tùy chỉnh hoặc bước xử lý sau khi nhóm; không thể dùng `Collectors.filtering` của Java 9.

### 11.3. Đếm số phần tử từng nhóm

Nếu chỉ cần số lượng, không tồn tại "thứ tự phần tử bên trong nhóm" vì giá trị nhóm không phải collection:

```java
LinkedHashMap<String, Long> demTheoDanhMuc =
    donHang.stream().collect(
        Collectors.groupingBy(
            DonHang::getDanhMuc,
            LinkedHashMap::new,
            Collectors.counting()
        )
    );

System.out.println(new ArrayList<>(demTheoDanhMuc.keySet()));
// [Sách, Điện tử, Đồ dùng]
System.out.println(demTheoDanhMuc.get("Sách")); // 3
```

Ở đây chỉ có tầng thứ tự khóa `LinkedHashMap`; `counting` trả `Long` cho từng nhóm.

## 12. Nguồn rỗng, khóa vắng mặt và khóa `null`

`groupingBy` chỉ tạo nhóm cho các khóa thực sự xuất hiện trong pipeline.

```java
import java.util.Collections;

List<DonHang> rong = Collections.emptyList();

LinkedHashMap<String, List<DonHang>> nhomRong =
    rong.stream().collect(
        Collectors.groupingBy(
            DonHang::getDanhMuc,
            LinkedHashMap::new,
            Collectors.toList()
        )
    );

System.out.println(nhomRong.isEmpty()); // true
```

Không có khóa nào để sắp xếp hoặc duyệt. Nếu giao diện phải hiển thị đủ các danh mục kể cả khi không có đơn, lấy **danh sách khóa chuẩn từ nghiệp vụ** rồi bổ sung nhóm trống theo quy tắc hiển thị, thay vì mong `groupingBy` tự tạo khóa.

`groupingBy` cũng không chấp nhận giá trị phân loại `null` trong triển khai JDK chuẩn. Nếu một `DonHang` thiếu danh mục, hãy xử lý tường minh:

```java
LinkedHashMap<String, List<DonHang>> nhom = donHang.stream()
    .collect(Collectors.groupingBy(
        d -> d.getDanhMuc() == null
            ? "Chưa phân loại"
            : d.getDanhMuc(),
        LinkedHashMap::new,
        Collectors.toList()
    ));
```

Quy tắc trên giữ bản ghi chưa phân loại trong một nhóm cụ thể. Nếu chọn `filter` để bỏ dữ liệu thiếu danh mục, cần lưu ý cả **thứ tự các khóa còn lại** và số lượng bản ghi đều có thể thay đổi.

## 13. Kiểm thử thứ tự: xác minh hai tầng riêng biệt

Một kiểm thử chỉ so sánh kích thước map hoặc số lượng phần tử là **chưa đủ** để khẳng định thứ tự đúng. Hãy kiểm tra **danh sách khóa** và **danh sách mã của từng nhóm**.

Ví dụ kiểm thử Java 8, đặt trong `main` của lớp `NhomDonHangCoThuTu`:

```java
LinkedHashMap<String, ArrayList<DonHang>> nhom = donHang.stream()
    .collect(Collectors.groupingBy(
        DonHang::getDanhMuc,
        LinkedHashMap::new,
        Collectors.toCollection(ArrayList::new)
    ));

List<String> khoaMongDoi = Arrays.asList(
    "Sách", "Điện tử", "Đồ dùng"
);

List<String> maSachMongDoi = Arrays.asList(
    "DH01", "DH03", "DH06"
);

List<String> khoaThucTe = new ArrayList<>(nhom.keySet());

List<String> maSachThucTe = nhom.get("Sách").stream()
    .map(DonHang::getMa)
    .collect(Collectors.toList());

if (!khoaMongDoi.equals(khoaThucTe)) {
    throw new AssertionError(
        "Sai thứ tự nhóm: " + khoaThucTe
    );
}

if (!maSachMongDoi.equals(maSachThucTe)) {
    throw new AssertionError(
        "Sai thứ tự đơn Sách: " + maSachThucTe
    );
}

System.out.println("PASS: cả hai tầng thứ tự");
```

**Vì sao không so sánh toàn bộ `Map` bằng `equals`?** `Map.equals` kiểm tra các cặp khóa–giá trị, **không phải thứ tự duyệt khóa**. Hai map có cùng dữ liệu nhưng thứ tự khóa khác nhau vẫn có thể bằng nhau. Tương tự, `Set.equals` không kiểm tra thứ tự chèn của `LinkedHashSet`.

Để kiểm tra thứ tự của `LinkedHashSet`, chuyển nó thành `ArrayList` rồi so sánh với danh sách mong đợi:

```java
LinkedHashSet<String> set = new LinkedHashSet<>(
    Arrays.asList("A", "B", "A", "C")
);

boolean dungThuTu = new ArrayList<>(set)
    .equals(Arrays.asList("A", "B", "C"));

System.out.println(dungThuTu); // true
```

Với dữ liệu lớn, test cũng nên bao gồm nhóm chỉ có một phần tử, khóa lặp lại không liên tiếp, bản ghi trùng, nguồn rỗng và thứ tự tie-breaker của comparator.

## 14. Hiệu năng, bộ nhớ và tài nguyên

Giữ encounter order không phải lúc nào cũng miễn phí:

- `LinkedHashMap` cần thêm cấu trúc liên kết để giữ thứ tự chèn khóa, so với map chỉ tối ưu tra cứu.
- `ArrayList` lưu mọi phần tử của từng nhóm; nếu chỉ cần số lượng hoặc tổng, dùng downstream `counting()` hoặc `summingLong()` sẽ tránh lưu các danh sách lớn.
- `LinkedHashSet` loại trùng và lưu thứ tự chèn, nhưng có overhead băm và liên kết; không nên dùng nếu nghiệp vụ vẫn cần mọi bản ghi, kể cả trùng.
- `sorted` thường phải quan sát toàn bộ dữ liệu đầu vào của bước sắp xếp, có thể tốn thời gian và bộ nhớ. Sắp xếp từng nhóm sau khi thu đôi khi giảm nhu cầu sắp xếp trên toàn bộ phần tử, nhưng hiệu quả thực tế phụ thuộc dữ liệu.
- `parallelStream()` có chi phí chia việc, phối hợp và ghép các map cục bộ. `groupingByConcurrent` có thể giảm một số chi phí trong trường hợp thích hợp, nhưng đánh đổi ràng buộc thứ tự.
- `collect` trên nguồn có thể vô hạn và không có điểm dừng có nguy cơ không hoàn thành hoặc cạn tài nguyên; cần giới hạn dữ liệu từ nguồn trước khi thu.

Nếu báo cáo chỉ cần `Map<DanhMuc, Long>` số lượng, không nên thu `Map<DanhMuc, List<DonHang>>` rồi gọi `size()` trên từng nhóm chỉ để đếm. Nếu thứ tự khóa là một yêu cầu hiển thị, hãy kiểm soát nó ở bước trình bày hoặc bằng `mapFactory` đúng loại.

Không có quy tắc rằng stream song song luôn nhanh hơn stream tuần tự. Với nguồn không lớn và nhu cầu giữ chặt thứ tự, pipeline tuần tự thường đơn giản, dễ kiểm thử và dễ dự đoán hơn.

## 15. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| `groupingBy(classifier)` in nhóm theo thứ tự không mong muốn | Map mặc định không cam kết thứ tự khóa | Dùng `groupingBy(classifier, LinkedHashMap::new, downstream)`. |
| Dùng `LinkedHashMap` nhưng phần tử trong nhóm vẫn không có thứ tự | Downstream là `toSet()` hoặc nguồn không có encounter order | Chọn `toList()` / `toCollection(ArrayList::new)` và nguồn có thứ tự. |
| Dùng `LinkedHashSet` làm mất đơn hàng trùng | Set chỉ giữ phần tử duy nhất | Chuyển sang `ArrayList` nếu phải giữ mọi bản ghi. |
| Chọn `TreeMap` và mong thứ tự xuất hiện đầu | `TreeMap` sắp xếp khóa, không giữ thứ tự chèn | Dùng `LinkedHashMap` nếu muốn first-seen. |
| `sorted` trước `groupingBy` khiến thứ tự danh mục đổi | Sắp xếp toàn bộ nguồn thay đổi khóa nào được gặp trước | Chỉ sắp xếp list của từng nhóm nếu cần giữ thứ tự khóa cũ. |
| `Collectors.toList()` tạo list không đúng kiểu cụ thể mong muốn | API không cam kết `ArrayList` | Dùng `toCollection(ArrayList::new)`. |
| `parallelStream().forEach(map::put)` làm sai dữ liệu | Thay đổi map chia sẻ từ nhiều thread; `forEach` không cam kết thứ tự | Dùng collector có hợp đồng đúng. |
| `groupingByConcurrent` làm thay đổi thứ tự phần tử nhóm | Collector concurrent/unordered | Dùng `groupingBy` thường hoặc sắp xếp rõ ràng sau khi thu. |
| `HashSet.stream()` cho thứ tự nhóm khác kỳ vọng | Nguồn không có thứ tự được cam kết | Tạo nguồn ordered hoặc dùng `sorted` với comparator phù hợp. |
| Test `Map.equals` vượt qua nhưng UI hiển thị sai thứ tự | `Map.equals` không so sánh thứ tự duyệt | So sánh `new ArrayList<>(map.keySet())`. |
| Test `LinkedHashSet.equals` vượt qua dù thứ tự khác | `Set.equals` chỉ so phần tử, không so thứ tự | So sánh thứ tự qua `new ArrayList<>(set)`. |
| Nhóm có khóa `null` gây lỗi | Classifier trả `null` | Chuẩn hóa hoặc lọc dữ liệu thiếu khóa. |
| Không có nhóm sau `filter` | Nhóm không có phần tử hợp lệ nên không được tạo | Bổ sung nhóm trống nếu nghiệp vụ cần. |
| Thu nguồn vô hạn dẫn tới hết bộ nhớ | Không có điểm dừng trước collector | Giới hạn hoặc phân trang nguồn; tránh thu toàn bộ. |

## 16. Bài tập thực hành

Sử dụng lại sáu đơn hàng trong mục 3.

### Bài 1: Giữ thứ tự hai tầng

Viết một pipeline có kết quả `LinkedHashMap<String, ArrayList<DonHang>>`. Hãy xác định thứ tự khóa và thứ tự mã đơn trong nhóm "Sách".

### Bài 2: Loại khách hàng trùng nhưng giữ lần đầu

Tạo `LinkedHashMap<String, LinkedHashSet<String>>` chứa mã khách hàng theo danh mục. Nhóm "Sách" phải có những khách hàng nào, theo thứ tự nào? Tại sao mã `KH-A` không xuất hiện hai lần?

### Bài 3: Sắp xếp theo giá mà không đảo thứ tự nhóm

Giữ thứ tự khóa [Sách, Điện tử, Đồ dùng]. Tuy nhiên, trong mỗi nhóm, sắp xếp đơn theo `soTien` tăng dần. Có nên đặt `sorted(comparingLong(DonHang::getSoTien))` trước `groupingBy` không? Viết cách thực hiện đúng bằng `collectingAndThen` hoặc bước xử lý sau nhóm.

### Bài 4: Nguồn không có thứ tự

Nếu thay nguồn `List` bằng `HashSet`, `LinkedHashMap::new` có đủ bảo đảm thứ tự xuất hiện mà nghiệp vụ mong muốn không? Đề xuất cách đặt thứ tự xác định dựa trên `ma` của đơn hàng.

### Bài 5: Nhận diện lỗi trong kiểm thử

Một chương trình tạo hai `LinkedHashMap` cùng cặp khóa–giá trị nhưng thứ tự khóa lần lượt là [Sách, Điện tử] và [Điện tử, Sách]. `map1.equals(map2)` cho kết quả gì? Cần kiểm tra như thế nào để phát hiện thứ tự sai?

### Đáp án tham khảo

**Bài 1:**

```java
LinkedHashMap<String, ArrayList<DonHang>> nhom =
    donHang.stream().collect(
        Collectors.groupingBy(
            DonHang::getDanhMuc,
            LinkedHashMap::new,
            Collectors.toCollection(ArrayList::new)
        )
    );

// Khóa: [Sách, Điện tử, Đồ dùng]
// Nhóm Sách: [DH01, DH03, DH06]
```

**Bài 2:**

```java
LinkedHashMap<String, LinkedHashSet<String>> nhom =
    donHang.stream().collect(
        Collectors.groupingBy(
            DonHang::getDanhMuc,
            LinkedHashMap::new,
            Collectors.mapping(
                DonHang::getKhachHang,
                Collectors.toCollection(LinkedHashSet::new)
            )
        )
    );

System.out.println(nhom.get("Sách")); // [KH-A, KH-C]
```

`LinkedHashSet` loại lần xuất hiện `KH-A` thứ hai ở nhóm "Sách" theo hợp đồng bằng nhau của `String`.

**Bài 3:** Không nên sắp xếp toàn nguồn khi cần giữ thứ tự khóa xuất hiện đầu. Thu các nhóm vào `LinkedHashMap` rồi sắp xếp riêng từng `ArrayList`:

```java
LinkedHashMap<String, ArrayList<DonHang>> nhom =
    donHang.stream().collect(
        Collectors.groupingBy(
            DonHang::getDanhMuc,
            LinkedHashMap::new,
            Collectors.collectingAndThen(
                Collectors.toCollection(ArrayList::new),
                list -> {
                    list.sort(Comparator.comparingLong(DonHang::getSoTien));
                    return list;
                }
            )
        )
    );

// Khóa vẫn [Sách, Điện tử, Đồ dùng]
// Nhóm Sách trở thành [DH01, DH06, DH03]
```

**Bài 4:** Không. Nguồn `HashSet` không cam kết encounter order. Có thể dùng:

```java
LinkedHashMap<String, List<DonHang>> nhom =
    hashSetDonHang.stream()
        .sorted(Comparator.comparing(DonHang::getMa))
        .collect(Collectors.groupingBy(
            DonHang::getDanhMuc,
            LinkedHashMap::new,
            Collectors.toList()
        ));
```

Giả định `ma` là duy nhất hoặc comparator có thêm tiêu chí phụ để xác định thứ tự khi mã bằng nhau. Trong ứng dụng, biến `hashSetDonHang` phải là nguồn `Set<DonHang>` đã được khai báo phù hợp.

**Bài 5:** `Map.equals` cho `true` nếu hai map có cùng các ánh xạ khóa–giá trị, dù thứ tự chèn khác. Để kiểm tra thứ tự:

```java
boolean dungThuTu =
    new ArrayList<>(map1.keySet())
        .equals(Arrays.asList("Sách", "Điện tử"));
```

Tương tự, nếu cần kiểm tra thứ tự trong một `LinkedHashSet`, chuyển set thành list trước khi so sánh.

## 17. Tổng kết

Để giữ đúng thứ tự trong kết quả `groupingBy`, hãy quyết định **riêng hai tầng**:

```java
// 1. Nhóm theo thứ tự gặp; giữ mọi phần tử theo encounter order:
stream.collect(Collectors.groupingBy(
    classifier,
    LinkedHashMap::new,
    Collectors.toCollection(ArrayList::new)
));

// 2. Nhóm theo thứ tự gặp; giữ phần tử duy nhất theo lần xuất hiện đầu:
stream.collect(Collectors.groupingBy(
    classifier,
    LinkedHashMap::new,
    Collectors.toCollection(LinkedHashSet::new)
));
```

Các đoạn mẫu trên giả định có nguồn stream, classifier và các import phù hợp.

Ghi nhớ:

- **Thứ tự nhóm:** `LinkedHashMap` giữ thứ tự chèn khóa; `TreeMap` sắp xếp khóa; map mặc định của `groupingBy` không cam kết thứ tự khóa.
- **Thứ tự phần tử trong nhóm:** `toList` / `ArrayList` giữ encounter order của nguồn ordered; `LinkedHashSet` giữ thứ tự xuất hiện đầu của các giá trị duy nhất; `toSet` không cam kết thứ tự.
- **Thứ tự nguồn:** nếu nguồn không ordered hoặc pipeline gọi `unordered()`, không được kỳ vọng collector khôi phục một thứ tự không tồn tại.
- **Sắp xếp:** sắp xếp toàn stream có thể đổi cả thứ tự nhóm; sắp xếp từng list sau nhóm chỉ thay thứ tự phần tử trong nhóm.
- **Song song:** phân biệt thứ tự thực thi callback với thứ tự duyệt kết quả. `groupingByConcurrent` là collector unordered, không thích hợp nếu yêu cầu thứ tự bên trong nhóm.
- **Kiểm thử:** kiểm tra `keySet()` và các list theo thứ tự, không chỉ `Map.equals` hoặc `Set.equals`.

Khi hiểu hai tầng thứ tự này, bạn có thể xây dựng pipeline `filter`, `map`, `collect` và các phép phân nhóm phức tạp với kết quả nhất quán, dễ kiểm thử và phù hợp yêu cầu nghiệp vụ.
