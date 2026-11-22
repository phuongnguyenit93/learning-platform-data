# Phân nhóm dữ liệu bằng `Collectors.groupingBy`

## 1. Mục tiêu và bài toán

Trong **Java Stream API** (`JAVA_STREAM_API`), pipeline xử lý dữ liệu theo cách khai báo: lấy nguồn, thực hiện các phép trung gian lazy như `filter` và `map`, rồi kết thúc bằng `collect` hoặc `reduce`. Khi muốn tổ chức nhiều phần tử theo một thuộc tính chung, **`Collectors.groupingBy`** là một công cụ cốt lõi.

Ví dụ, từ danh sách đơn hàng, ta cần biết:

- Mỗi danh mục có những đơn nào?
- Có bao nhiêu đơn trong từng danh mục?
- Tổng doanh thu theo từng danh mục là bao nhiêu?
- Trong từng danh mục, có bao nhiêu đơn đã hoàn tất?
- Cần trả kết quả thành `Map` có thứ tự khóa như thế nào?

Bài này thuộc chương **Phân nhóm và phân hoạch**. Sau bài, bạn có thể dùng cả ba overload của `groupingBy`, kết hợp downstream collector, xử lý dữ liệu rỗng/khóa không hợp lệ và hiểu giới hạn về thứ tự, tài nguyên, hiệu năng và xử lý song song. Đây là nền tảng cho các nội dung nâng cao như collector tùy chỉnh và grouping song song.

## 2. Tư duy cơ bản: classifier biến phần tử thành khóa nhóm

`groupingBy` nhận một **hàm phân loại** (*classifier*), dùng để tính **khóa nhóm** từ mỗi phần tử. Những phần tử có khóa được coi là bằng nhau sẽ được đưa vào cùng một nhóm.

```text
                      classifier: lấy danh mục
                       │
Đơn DH01 (Sách)  ───────┼───────────────┐
Đơn DH02 (Đồ dùng) ─────┼───────────┐   │
Đơn DH03 (Sách)  ───────┼───────────│───┤
Đơn DH04 (Đồ dùng) ─────┼───────────┤   │
Đơn DH05 (Điện tử) ─────┼───────┐   │   │
Đơn DH06 (Sách)  ───────┼───────│───│───┤
                       ▼       ▼   ▼   ▼
                   Map<String, List<DonHang>>
                   "Điện tử" → [DH05]
                   "Đồ dùng" → [DH02, DH04]
                   "Sách"    → [DH01, DH03, DH06]
```

Cách nhìn tổng quát:

```java
Map<K, List<T>> ketQua = stream.collect(
    Collectors.groupingBy(phanTu -> khoaNhom)
);
```

- `T`: kiểu phần tử nguồn.
- `K`: kiểu khóa do classifier trả về.
- `Map<K, List<T>>`: ánh xạ mỗi khóa tới danh sách các phần tử thuộc khóa đó.

**Quan trọng:** `groupingBy` là một collector đưa vào terminal operation `collect`. Việc phân nhóm thực tế diễn ra khi `collect` tiêu thụ stream; nó không tự phát sinh một nguồn mới để tiếp tục xử lý như `map` hay `filter`.

## 3. Ví dụ Java 8 hoàn chỉnh: nhóm đơn hàng theo danh mục

Chạy đoạn chương trình sau bằng Java 8 trở lên:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class NhomDonHang {
    static final class DonHang {
        private final String ma;
        private final String danhMuc;
        private final long gia;
        private final boolean hoanTat;

        DonHang(String ma, String danhMuc, long gia, boolean hoanTat) {
            this.ma = ma;
            this.danhMuc = danhMuc;
            this.gia = gia;
            this.hoanTat = hoanTat;
        }

        public String getMa() {
            return ma;
        }

        public String getDanhMuc() {
            return danhMuc;
        }

        public long getGia() {
            return gia;
        }

        public boolean isHoanTat() {
            return hoanTat;
        }

        @Override
        public String toString() {
            return ma;
        }
    }

    static List<DonHang> duLieu() {
        return Arrays.asList(
            new DonHang("DH01", "Sách", 120_000L, true),
            new DonHang("DH02", "Đồ dùng", 80_000L, false),
            new DonHang("DH03", "Sách", 180_000L, true),
            new DonHang("DH04", "Đồ dùng", 50_000L, true),
            new DonHang("DH05", "Điện tử", 900_000L, false),
            new DonHang("DH06", "Sách", 70_000L, false)
        );
    }

    public static void main(String[] args) {
        List<DonHang> donHang = duLieu();

        Map<String, List<DonHang>> theoDanhMuc = donHang.stream()
            .collect(Collectors.groupingBy(DonHang::getDanhMuc));

        System.out.println(theoDanhMuc.get("Sách"));
        System.out.println(theoDanhMuc.get("Đồ dùng"));
        System.out.println(theoDanhMuc.get("Điện tử"));
    }
}
```

Kết quả:

```text
[DH01, DH03, DH06]
[DH02, DH04]
[DH05]
```

Ở đây:

1. `donHang.stream()` tạo `Stream<DonHang>`.
2. `DonHang::getDanhMuc` là classifier kiểu `Function<DonHang, String>`.
3. `groupingBy` tạo `Map<String, List<DonHang>>`.
4. Mỗi danh mục trở thành một khóa của `Map`.
5. Những đơn có cùng danh mục được tích lũy vào danh sách thuộc khóa đó.

Các ví dụ tiếp theo giả định **lớp `DonHang` và phương thức `duLieu()` ở trên**, và được đặt trong `main` hoặc phương thức khác của chính lớp `NhomDonHang`:

```java
List<DonHang> donHang = duLieu();
```

Ví dụ in giá trị theo từng khóa một cách tường minh để không phụ thuộc thứ tự duyệt khóa của kiểu `Map` mặc định.

## 4. Ba overload quan trọng của `groupingBy`

Có ba cách gọi phổ biến từ Java 8. Chữ ký dưới đây lược bỏ chi tiết không ảnh hưởng tới việc đọc:

```java
// 1. Chọn classifier, giữ toàn bộ phần tử từng nhóm.
groupingBy(Function<? super T, ? extends K> classifier)

// 2. Chọn classifier và downstream collector cho từng nhóm.
groupingBy(
    Function<? super T, ? extends K> classifier,
    Collector<? super T, A, D> downstream
)

// 3. Chọn classifier, loại Map kết quả và downstream collector.
groupingBy(
    Function<? super T, ? extends K> classifier,
    Supplier<M> mapFactory,
    Collector<? super T, A, D> downstream
)
```

So sánh:

| Overload | Kiểu kết quả điển hình | Khi sử dụng |
| --- | --- | --- |
| `groupingBy(classifier)` | `Map<K, List<T>>` | Muốn giữ các phần tử của mỗi nhóm. |
| `groupingBy(classifier, downstream)` | `Map<K, D>` | Muốn đếm, tính tổng, lấy tên, thống kê hoặc rút gọn từng nhóm. |
| `groupingBy(classifier, mapFactory, downstream)` | Một loại `Map` cụ thể | Cần kiểm soát kiểu map, ví dụ `LinkedHashMap` hoặc `TreeMap`. |

Trong overload hai và ba tham số, kiểu `D` là **kết quả của downstream collector**, không nhất thiết là `List<T>`. Vì vậy `groupingBy` là công cụ phân nhóm có thể kết hợp phép tổng hợp, không chỉ là thao tác chia dữ liệu vào các list.

Với overload chỉ có classifier, kết quả tương đương về mục đích với downstream `Collectors.toList()`. Tuy nhiên, **không có bảo đảm** về kiểu `Map` cụ thể, tính có thể sửa, thread-safety hoặc serializability của `Map` và `List` kết quả. Không được dựa vào việc triển khai hiện tại tình cờ trả `HashMap` hoặc `ArrayList`.

## 5. Đếm số phần tử trong mỗi nhóm với `counting()`

Nếu chỉ muốn thống kê số lượng, không cần lưu tất cả phần tử vào các danh sách:

```java
Map<String, Long> soDon = donHang.stream()
    .collect(Collectors.groupingBy(
        DonHang::getDanhMuc,
        Collectors.counting()
    ));

System.out.println(soDon.get("Sách"));    // 3
System.out.println(soDon.get("Đồ dùng")); // 2
System.out.println(soDon.get("Điện tử")); // 1
```

Đọc kiểu:

```text
Stream<DonHang>
    └─ classifier: DonHang -> String
    └─ downstream: nhiều DonHang -> Long
                     │
                     ▼
             Map<String, Long>
```

`Collectors.counting()` trả `Long`, nên `Map<String, Long>` là kiểu đúng. Nếu viết `Map<String, Integer>` sẽ gặp lỗi biên dịch.

**Không nhầm** `donHang.stream().count()` với `groupingBy(..., counting())`:

- `count()` trả một số `long` cho **toàn bộ stream**.
- `groupingBy(..., counting())` trả một `Map` chứa **số đếm cho từng khóa**.

Nếu thêm bộ lọc, chỉ các phần tử vượt qua `filter` mới đóng góp vào các nhóm:

```java
Map<String, Long> soDonHoanTat = donHang.stream()
    .filter(DonHang::isHoanTat)
    .collect(Collectors.groupingBy(
        DonHang::getDanhMuc,
        Collectors.counting()
    ));

System.out.println(soDonHoanTat.get("Sách"));    // 2
System.out.println(soDonHoanTat.get("Đồ dùng")); // 1
System.out.println(soDonHoanTat.get("Điện tử")); // null (không có khóa)
```

`get("Điện tử") == null` biểu thị **không có nhóm tương ứng**, khác với một nhóm có số đếm bằng 0. Nếu yêu cầu báo cáo phải hiển thị cả các danh mục không có đơn hoàn tất, hãy bổ sung các khóa theo danh sách danh mục nghiệp vụ ở bước riêng.

## 6. Tính tổng và thống kê theo từng khóa

### 6.1. Tổng giá trị mỗi danh mục

`Collectors.summingLong` nhận hàm biến phần tử thành giá trị `long` rồi tính tổng từng nhóm:

```java
Map<String, Long> tongGiaTri = donHang.stream()
    .collect(Collectors.groupingBy(
        DonHang::getDanhMuc,
        Collectors.summingLong(DonHang::getGia)
    ));

System.out.println(tongGiaTri.get("Sách"));    // 370000
System.out.println(tongGiaTri.get("Đồ dùng")); // 130000
System.out.println(tongGiaTri.get("Điện tử")); // 900000
```

Dữ liệu trong ví dụ tính bằng đơn vị giả định; ở bài toán tiền tệ thực tế cần chọn kiểu dữ liệu, quy tắc làm tròn và giới hạn tràn số phù hợp. `long` rộng hơn `int` nhưng vẫn có thể tràn khi tổng lớn hơn `Long.MAX_VALUE`.

### 6.2. Trung bình theo danh mục

`Collectors.averagingLong` trả về `Double`, ngay cả khi đầu vào là `long`:

```java
Map<String, Double> giaTrungBinh = donHang.stream()
    .collect(Collectors.groupingBy(
        DonHang::getDanhMuc,
        Collectors.averagingLong(DonHang::getGia)
    ));

System.out.println(giaTrungBinh.get("Sách"));    // 123333.33333333333
System.out.println(giaTrungBinh.get("Đồ dùng")); // 65000.0
System.out.println(giaTrungBinh.get("Điện tử")); // 900000.0
```

`double` có sai số dấu phẩy động. Nếu cần tính số tiền trung bình theo quy tắc làm tròn nghiệp vụ, không dùng kết quả `Double` như biểu diễn tiền chính xác tuyệt đối.

### 6.3. Nhiều thống kê bằng `summarizingLong`

`LongSummaryStatistics` cung cấp số lượng, tổng, min, max và trung bình trong cùng một kết quả:

```java
import java.util.LongSummaryStatistics;

Map<String, LongSummaryStatistics> thongKe = donHang.stream()
    .collect(Collectors.groupingBy(
        DonHang::getDanhMuc,
        Collectors.summarizingLong(DonHang::getGia)
    ));

LongSummaryStatistics sach = thongKe.get("Sách");

System.out.println(sach.getCount());   // 3
System.out.println(sach.getSum());     // 370000
System.out.println(sach.getMin());     // 70000
System.out.println(sach.getMax());     // 180000
```

Với `summingLong`, `averagingLong` hoặc `summarizingLong`, bạn không cần tạo các `List<DonHang>` chỉ để tính số liệu. Đây là cách khai báo thường tiết kiệm bộ nhớ hơn khi không cần giữ lại toàn bộ các bản ghi.

## 7. Biến đổi phần tử bên trong từng nhóm bằng `mapping()`

Khi chỉ muốn giữ **mã đơn hàng** thay vì toàn bộ đối tượng, sử dụng downstream `mapping`:

```java
Map<String, List<String>> maTheoDanhMuc = donHang.stream()
    .collect(Collectors.groupingBy(
        DonHang::getDanhMuc,
        Collectors.mapping(
            DonHang::getMa,
            Collectors.toList()
        )
    ));

System.out.println(maTheoDanhMuc.get("Sách"));
// [DH01, DH03, DH06]
```

`Collectors.mapping(mapper, downstream)` chuyển từng phần tử **sau khi đã phân nhóm** thành giá trị phù hợp với downstream collector. Kiểu kết quả thay đổi như sau:

```text
Stream<DonHang>
  ├─ classifier: DanhMuc → String
  └─ mapping: DonHang → String (mã đơn)
      └─ toList() → List<String>
             │
             ▼
     Map<String, List<String>>
```

Có thể thay `Collectors.toList()` bằng `Collectors.toSet()` nếu chỉ cần các mã duy nhất:

```java
import java.util.Set;

Map<String, Set<String>> maDuyNhat = donHang.stream()
    .collect(Collectors.groupingBy(
        DonHang::getDanhMuc,
        Collectors.mapping(
            DonHang::getMa,
            Collectors.toSet()
        )
    ));
```

**Lưu ý:** `Collectors.toSet()` không bảo đảm thứ tự duyệt của set. Nếu cần giữ thứ tự xuất hiện đầu tiên của các mã trong từng nhóm, hãy chọn rõ `LinkedHashSet`:

```java
import java.util.LinkedHashSet;

Map<String, LinkedHashSet<String>> maCoThuTu = donHang.stream()
    .collect(Collectors.groupingBy(
        DonHang::getDanhMuc,
        Collectors.mapping(
            DonHang::getMa,
            Collectors.toCollection(LinkedHashSet::new)
        )
    ));

System.out.println(maCoThuTu.get("Sách"));
// [DH01, DH03, DH06]
```

Trên nguồn `List` có thứ tự và pipeline tuần tự, thứ tự trong collection của mỗi nhóm phản ánh thứ tự gặp các phần tử thuộc nhóm đó.

## 8. Tạo phân nhóm nhiều cấp

Có thể đặt một `groupingBy` khác làm downstream collector để phân nhóm hai chiều. Ví dụ: **danh mục → trạng thái hoàn tất → danh sách đơn hàng**.

```java
Map<String, Map<Boolean, List<DonHang>>> theoDanhMucVaTrangThai =
    donHang.stream().collect(
        Collectors.groupingBy(
            DonHang::getDanhMuc,
            Collectors.groupingBy(DonHang::isHoanTat)
        )
    );

System.out.println(
    theoDanhMucVaTrangThai.get("Sách").get(true)
); // [DH01, DH03]

System.out.println(
    theoDanhMucVaTrangThai.get("Sách").get(false)
); // [DH06]
```

Kiểu có nhiều tầng `Map` vì mỗi downstream collector lại trả về một map. Có thể thay danh sách ở tầng cuối bằng số đếm:

```java
Map<String, Map<Boolean, Long>> demTheoDanhMucVaTrangThai =
    donHang.stream().collect(
        Collectors.groupingBy(
            DonHang::getDanhMuc,
            Collectors.groupingBy(
                DonHang::isHoanTat,
                Collectors.counting()
            )
        )
    );

System.out.println(
    demTheoDanhMucVaTrangThai.get("Sách").get(true)
); // 2
```

Không phải mọi nhóm đều có đủ cả hai trạng thái. Ví dụ, danh mục "Điện tử" chỉ có đơn chưa hoàn tất, nên map con có thể **không có khóa `true`**:

```java
System.out.println(
    demTheoDanhMucVaTrangThai.get("Điện tử").get(true)
); // null
```

Cần phân biệt **khóa vắng mặt** với **giá trị thống kê 0**, nhất là khi giao tiếp với báo cáo hoặc JSON. Nếu muốn đảm bảo cả hai khóa Boolean trong từng nhóm đã xuất hiện, sử dụng `partitioningBy` làm downstream:

```java
Map<String, Map<Boolean, Long>> demHaiTrangThai =
    donHang.stream().collect(
        Collectors.groupingBy(
            DonHang::getDanhMuc,
            Collectors.partitioningBy(
                DonHang::isHoanTat,
                Collectors.counting()
            )
        )
    );

System.out.println(
    demHaiTrangThai.get("Điện tử").get(true)
); // 0
```

Ở đây khóa danh mục chỉ được tạo khi có phần tử thuộc danh mục đó, nhưng trong map con của mỗi danh mục đã có, `partitioningBy` cung cấp cả nhánh `true` và `false`.

## 9. Chọn loại `Map` với overload ba tham số

Mặc định, `groupingBy(classifier)` **không cam kết** `Map` thuộc lớp nào hoặc thứ tự duyệt các khóa. Do đó, không nên dựa vào thứ tự in của:

```java
Map<String, List<DonHang>> ketQua = donHang.stream()
    .collect(Collectors.groupingBy(DonHang::getDanhMuc));

System.out.println(ketQua); // Không cam kết thứ tự các khóa.
```

Nếu cần giữ **thứ tự các danh mục xuất hiện lần đầu** trong một nguồn `List` có thứ tự, dùng `LinkedHashMap` và stream tuần tự:

```java
import java.util.LinkedHashMap;

LinkedHashMap<String, List<DonHang>> theoThuTuXuatHien =
    donHang.stream().collect(
        Collectors.groupingBy(
            DonHang::getDanhMuc,
            LinkedHashMap::new,
            Collectors.toList()
        )
    );

System.out.println(theoThuTuXuatHien.keySet());
// [Sách, Đồ dùng, Điện tử]
```

`LinkedHashMap` giữ thứ tự chèn khóa; ở pipeline tuần tự có thứ tự, đó là thứ tự xuất hiện đầu tiên của từng danh mục.

Nếu cần sắp xếp khóa theo **thứ tự tự nhiên** của `String`, dùng `TreeMap`:

```java
import java.util.TreeMap;

TreeMap<String, Long> theoKhoaSapXep =
    donHang.stream().collect(
        Collectors.groupingBy(
            DonHang::getDanhMuc,
            TreeMap::new,
            Collectors.counting()
        )
    );

System.out.println(theoKhoaSapXep.firstKey());
```

`TreeMap` mặc định dùng so sánh tự nhiên của `String` theo thứ tự Unicode; không có nghĩa là sắp xếp ngôn ngữ tiếng Việt đúng quy tắc từ điển. Khi cần thứ tự đặc thù theo locale, hãy cung cấp `Comparator` phù hợp thông qua map factory.

**Ghi nhớ:** loại map quyết định cách duyệt **các khóa nhóm**, còn downstream collector quyết định dữ liệu **bên trong từng nhóm**. `LinkedHashMap<String, Set<DonHang>>` chẳng hạn có thứ tự khóa nhưng `Set` thường vẫn không cam kết thứ tự giá trị.

## 10. `groupingBy` và `partitioningBy` khác nhau ra sao?

Hai phương thức đều phân loại phần tử nhưng có mục đích riêng.

| Đặc điểm | `groupingBy(classifier)` | `partitioningBy(predicate)` |
| --- | --- | --- |
| Khóa | Loại `K` tùy ý | Chỉ hai giá trị Boolean: `true`/`false` |
| Hàm đầu vào | `Function<T, K>` | `Predicate<T>` |
| Số nhóm có thể có | Từ 0 đến số khóa phân biệt | Luôn có hai khóa Boolean trong map trả về |
| Nguồn rỗng | Map rỗng | Cả hai nhánh tồn tại với kết quả downstream rỗng/tương ứng |
| Trường hợp điển hình | Phân theo danh mục, tỉnh, trạng thái nhiều mức | Phân đạt/không đạt, đã hoàn tất/chưa hoàn tất |

Ví dụ partition:

```java
Map<Boolean, List<DonHang>> theoHoanTat = donHang.stream()
    .collect(Collectors.partitioningBy(DonHang::isHoanTat));

System.out.println(theoHoanTat.get(true));
// [DH01, DH03, DH04]

System.out.println(theoHoanTat.get(false));
// [DH02, DH05, DH06]
```

Nếu dùng `groupingBy(DonHang::isHoanTat)`, kết quả có thể giống khi dữ liệu tồn tại ở cả hai nhánh, nhưng **không có cam kết xuất hiện hai khóa** nếu một nhánh không có phần tử.

Ví dụ trên nguồn rỗng:

```java
import java.util.Collections;

List<DonHang> rong = Collections.emptyList();

Map<Boolean, List<DonHang>> chia = rong.stream()
    .collect(Collectors.partitioningBy(DonHang::isHoanTat));

Map<Boolean, List<DonHang>> nhom = rong.stream()
    .collect(Collectors.groupingBy(DonHang::isHoanTat));

System.out.println(chia.containsKey(true));  // true
System.out.println(chia.containsKey(false)); // true
System.out.println(nhom.isEmpty());          // true
```

## 11. Dữ liệu rỗng, khóa null và chất lượng dữ liệu

### 11.1. Nguồn rỗng

Trên một stream rỗng, `groupingBy` không tạo các nhóm vắng mặt:

```java
Map<String, List<DonHang>> rong = java.util.stream.Stream
    .<DonHang>empty()
    .collect(Collectors.groupingBy(DonHang::getDanhMuc));

System.out.println(rong.isEmpty()); // true
```

Ngay cả khi downstream là `counting()` hoặc `summingLong()`, nó không tự tạo kết quả 0 cho tất cả các danh mục có thể có. Để làm báo cáo đủ danh mục, cần danh sách khóa chuẩn từ nghiệp vụ và xử lý bổ sung.

### 11.2. Classifier trả về `null`

Không nên trả `null` làm khóa phân nhóm. Các triển khai JDK thông dụng của `Collectors.groupingBy` không chấp nhận khóa phân loại `null` và có thể ném `NullPointerException` khi thu thập, dù một số loại `Map` thuần túy cho phép khóa `null`.

Giả sử dữ liệu có thể thiếu danh mục, một cách xử lý rõ nghĩa là **chuẩn hóa khóa**:

```java
Map<String, List<DonHang>> theoDanhMuc = donHang.stream()
    .collect(Collectors.groupingBy(d -> {
        String danhMuc = d.getDanhMuc();
        return danhMuc == null ? "Chưa phân loại" : danhMuc;
    }));
```

Hoặc nếu nghiệp vụ yêu cầu bỏ bản ghi thiếu danh mục, hãy lọc trước:

```java
Map<String, List<DonHang>> hopLe = donHang.stream()
    .filter(d -> d.getDanhMuc() != null)
    .collect(Collectors.groupingBy(DonHang::getDanhMuc));
```

Hai cách có **ý nghĩa dữ liệu khác nhau**: cách đầu giữ đơn chưa phân loại, cách sau bỏ chúng. Hãy chọn theo yêu cầu, không âm thầm mất dữ liệu.

### 11.3. Khóa là đối tượng tùy chỉnh

`Map` xác định khóa trùng theo `equals` và `hashCode` (trừ các map dùng comparator hoặc cơ chế đặc biệt). Nếu classifier trả về đối tượng làm khóa, hãy dùng thuộc tính định danh ổn định và triển khai `equals`/`hashCode` nhất quán.

Tránh sửa thuộc tính tham gia vào hash code sau khi khóa đã được đặt trong map. Hành vi tra cứu và phân nhóm có thể sai nếu khóa có thể đổi giá trị trong khi đang được sử dụng.

## 12. Tính lazy, trạng thái và hiệu năng

`groupingBy` làm việc bên trong `collect`: **nó phải tiêu thụ dữ liệu cần phân nhóm** để xác định các nhóm và kết quả downstream. Các thao tác `filter`/`map` phía trước vẫn là intermediate lazy, chỉ thực sự chạy khi terminal `collect` yêu cầu.

Nếu muốn thống kê tổng hợp, tránh lưu toàn bộ phần tử không cần thiết:

```java
// Giữ mọi đơn hàng theo danh mục:
Map<String, List<DonHang>> dayDu = donHang.stream()
    .collect(Collectors.groupingBy(DonHang::getDanhMuc));

// Chỉ giữ số lượng theo danh mục:
Map<String, Long> soLuong = donHang.stream()
    .collect(Collectors.groupingBy(
        DonHang::getDanhMuc,
        Collectors.counting()
    ));
```

Cách thứ nhất cần không gian để giữ các tham chiếu tới đơn hàng trong các danh sách; cách thứ hai chủ yếu giữ khóa và giá trị đếm. Cả hai đều cần dung lượng tăng theo số lượng khóa phân biệt.

**Không coi `collect(groupingBy(...))` là một cách xử lý vô hạn dữ liệu:** nếu nguồn có thể vô hạn và không được giới hạn, thao tác thu thập có thể không bao giờ hoàn tất hoặc cạn bộ nhớ.

Ví dụ có giới hạn:

```java
import java.util.stream.IntStream;

Map<Integer, Long> theoSoDu = IntStream.iterate(1, n -> n + 1)
    .limit(100)
    .boxed()
    .collect(Collectors.groupingBy(
        n -> n % 3,
        Collectors.counting()
    ));

System.out.println(theoSoDu.get(0)); // 33
System.out.println(theoSoDu.get(1)); // 34
System.out.println(theoSoDu.get(2)); // 33
```

Lưu ý số phần tử thực sự được tính **sau** các bộ lọc và giới hạn. Đưa `limit` trước hay sau `filter` có thể làm thay đổi dữ liệu được phân nhóm.

## 13. Phân nhóm trong parallel stream

`groupingBy` có thể được dùng trên một `parallelStream()` đúng hợp đồng:

```java
Map<String, Long> tongSongSong = donHang.parallelStream()
    .collect(Collectors.groupingBy(
        DonHang::getDanhMuc,
        Collectors.summingLong(DonHang::getGia)
    ));

System.out.println(tongSongSong.get("Sách")); // 370000
```

Collector có thể tạo nhiều vùng tích lũy riêng rồi **ghép các map nhóm**. Việc ghép có chi phí, đặc biệt khi số lượng nhóm lớn. `groupingBy` không phải collector concurrent; muốn tối ưu cho một số tình huống song song, Java có `groupingByConcurrent`:

```java
import java.util.concurrent.ConcurrentMap;

ConcurrentMap<String, Long> tongConcurrent = donHang.parallelStream()
    .collect(Collectors.groupingByConcurrent(
        DonHang::getDanhMuc,
        Collectors.summingLong(DonHang::getGia)
    ));
```

**Phân biệt những điều được bảo đảm:**

- `groupingByConcurrent` tạo một collector **concurrent** và **unordered**; không dựa vào thứ tự phần tử trong từng nhóm.
- `groupingBy` thông thường có thể bảo toàn ngữ nghĩa encounter order của các nhóm giá trị trên nguồn có thứ tự và collector downstream phù hợp, nhưng **không cam kết thứ tự duyệt khóa** của map mặc định.
- Kết quả là `ConcurrentMap` không có nghĩa mọi đối tượng giá trị bên trong đều là collection thread-safe cho các thao tác chỉnh sửa sau khi collect xong.
- Hiệu năng phụ thuộc số lượng nhóm, độ lệch phân bố nhóm, downstream collector và môi trường chạy. Không nên giả định `parallelStream()` hoặc `groupingByConcurrent` luôn nhanh hơn.

Tránh cập nhật một `HashMap` hay `ArrayList` dùng chung từ `parallelStream().forEach(...)` để tự phân nhóm; đó là nguồn gây lỗi race condition và sai dữ liệu. Dùng collector phù hợp giúp quá trình tích lũy tuân thủ cơ chế của Stream API.

## 14. `groupingBy` so với `toMap`

Hai collector đều cho kết quả dạng `Map` nhưng giải quyết bài toán khác nhau:

| Nhu cầu | Collector phù hợp | Đặc điểm |
| --- | --- | --- |
| Một khóa có thể có **nhiều phần tử** | `groupingBy` | Gom các phần tử cùng khóa; mặc định tạo list. |
| Mỗi khóa cần đúng **một giá trị**, đầu vào không có khóa trùng | `toMap(keyMapper, valueMapper)` | Khóa trùng thường gây `IllegalStateException` nếu không có hàm gộp. |
| Khóa trùng cần gộp thành một giá trị duy nhất | `toMap(keyMapper, valueMapper, mergeFunction)` | Cần định nghĩa phép gộp giá trị. |
| Tổng hoặc số đếm **theo nhóm** | `groupingBy(..., summingLong/counting)` | Nêu rõ ý định thống kê theo nhóm. |

Ví dụ `toMap` không có hàm gộp sẽ không phù hợp nếu nhiều đơn cùng danh mục:

```java
// KHÔNG NÊN CHẠY: có nhiều đơn cùng danh mục, sẽ gặp lỗi
// IllegalStateException vì khóa trùng.
Map<String, DonHang> sai = donHang.stream()
    .collect(Collectors.toMap(
        DonHang::getDanhMuc,
        d -> d
    ));
```

Nếu yêu cầu là "danh mục → danh sách đơn", `groupingBy` diễn đạt trực tiếp và an toàn hơn.

## 15. Lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `Map<String, Integer>` không biên dịch với `counting()` | `counting()` trả `Long` | Dùng `Map<String, Long>`. |
| `get("Điện tử")` trả `null` sau khi lọc | Không có nhóm nào cho khóa đó | Kiểm tra `containsKey` hoặc `getOrDefault`; bổ sung khóa nếu báo cáo cần. |
| Thứ tự khóa thay đổi khi in map | `groupingBy` mặc định không cam kết thứ tự map | Dùng `LinkedHashMap`/`TreeMap` qua map factory. |
| `NullPointerException` khi phân nhóm | Classifier có thể trả khóa `null` | Chuẩn hóa/loại bản ghi thiếu khóa trước khi collect. |
| Đếm nhóm chỉ có một con số tổng | Gọi `stream.count()` thay vì downstream `counting` | Dùng `groupingBy(classifier, counting())`. |
| Nhóm chỉ có `true` nhưng thiếu `false` | `groupingBy` không tự tạo khóa vắng mặt | Nếu muốn cả hai nhánh, dùng `partitioningBy`. |
| `toSet` làm mất thứ tự mã trong nhóm | `Collectors.toSet()` không cam kết thứ tự | Dùng `toCollection(LinkedHashSet::new)`. |
| Sai số tiền trung bình | `averagingLong` trả `Double` | Thiết kế chính sách chính xác/ làm tròn nghiệp vụ. |
| Dữ liệu sai khi phân nhóm song song thủ công | Cùng sửa cấu trúc chung từ nhiều thread | Dùng collector và tránh tác dụng phụ trong classifier. |
| Hết bộ nhớ khi giữ toàn bộ bản ghi | `groupingBy` mặc định lưu list từng nhóm | Chỉ dùng downstream thống kê nếu không cần bản ghi. |
| Ngữ nghĩa khóa không ổn định | `equals`/`hashCode` không nhất quán hoặc khóa bị sửa | Dùng khóa bất biến, định nghĩa so sánh rõ ràng. |

## 16. Bài tập tự thực hành

Dùng lại tập sáu đơn hàng trong mục 3.

### Bài 1: Phân nhóm và đếm

Viết `groupingBy` để tạo `Map<String, Long>` đếm số đơn trong từng danh mục. Dự đoán số lượng của "Sách", "Đồ dùng" và "Điện tử".

### Bài 2: Tổng giá trị từng nhóm

Tạo `Map<String, Long>` chứa tổng `gia` theo danh mục, **không tạo `List<DonHang>` trung gian**. So sánh với kết quả ở mục 6.

### Bài 3: Chỉ lấy mã và giữ thứ tự

Tạo `Map<String, List<String>>` sao cho mỗi danh mục ánh xạ tới danh sách **mã đơn hàng**, giữ thứ tự gặp trong nguồn `List`. Nhóm "Sách" phải có `[DH01, DH03, DH06]`.

### Bài 4: Phân nhóm lồng nhau

Tạo `Map<String, Map<Boolean, Long>>` chứa số đơn theo danh mục và trạng thái hoàn tất. Khi hỏi nhóm "Điện tử" và trạng thái `true`, vì sao có thể nhận `null`? Muốn có giá trị 0 thì đổi downstream bằng gì?

### Bài 5: Kiểm soát thứ tự khóa và nguồn rỗng

Dùng `LinkedHashMap::new` để đảm bảo thứ tự khóa trong một pipeline tuần tự từ `List`. Nguồn `Collections.<DonHang>emptyList()` được phân nhóm thì có bao nhiêu khóa? Nếu giao diện yêu cầu luôn hiển thị cả ba danh mục, cần bổ sung bước gì?

### Đáp án tham khảo

**Bài 1:**

```java
Map<String, Long> dem = donHang.stream()
    .collect(Collectors.groupingBy(
        DonHang::getDanhMuc,
        Collectors.counting()
    ));

// Sách = 3, Đồ dùng = 2, Điện tử = 1
```

**Bài 2:**

```java
Map<String, Long> tong = donHang.stream()
    .collect(Collectors.groupingBy(
        DonHang::getDanhMuc,
        Collectors.summingLong(DonHang::getGia)
    ));

// Sách = 370000, Đồ dùng = 130000, Điện tử = 900000
```

**Bài 3:**

```java
Map<String, List<String>> ma = donHang.stream()
    .collect(Collectors.groupingBy(
        DonHang::getDanhMuc,
        Collectors.mapping(
            DonHang::getMa,
            Collectors.toList()
        )
    ));

System.out.println(ma.get("Sách")); // [DH01, DH03, DH06]
```

**Bài 4:**

```java
Map<String, Map<Boolean, Long>> thongKe =
    donHang.stream().collect(
        Collectors.groupingBy(
            DonHang::getDanhMuc,
            Collectors.groupingBy(
                DonHang::isHoanTat,
                Collectors.counting()
            )
        )
    );
```

Khóa `true` không xuất hiện ở nhóm "Điện tử" vì không có đơn nào hoàn tất. Muốn luôn có hai nhánh Boolean, đổi collector bên trong thành `Collectors.partitioningBy(DonHang::isHoanTat, Collectors.counting())`.

**Bài 5:**

```java
LinkedHashMap<String, List<DonHang>> nhom =
    donHang.stream().collect(
        Collectors.groupingBy(
            DonHang::getDanhMuc,
            LinkedHashMap::new,
            Collectors.toList()
        )
    );

System.out.println(nhom.keySet());
// [Sách, Đồ dùng, Điện tử]
```

Stream rỗng được `groupingBy` thu thành map không có khóa. Nếu giao diện cần đủ các danh mục ngay cả khi không có đơn, phải lấy danh sách danh mục hợp lệ từ nghiệp vụ rồi điền các kết quả rỗng hoặc 0 theo hợp đồng, không mong `groupingBy` tự tạo nhóm.

## 17. Ghi nhớ

`Collectors.groupingBy` tổ chức các phần tử Stream theo **khóa do classifier trả về**. Cùng một classifier có thể tạo nhiều kiểu kết quả tùy downstream collector:

```java
// Danh mục -> danh sách đơn
groupingBy(DonHang::getDanhMuc)

// Danh mục -> số lượng đơn
groupingBy(DonHang::getDanhMuc, counting())

// Danh mục -> tổng giá trị
groupingBy(DonHang::getDanhMuc, summingLong(DonHang::getGia))

// Danh mục -> danh sách mã
groupingBy(DonHang::getDanhMuc, mapping(DonHang::getMa, toList()))

// Danh mục -> trạng thái -> số lượng
groupingBy(DonHang::getDanhMuc,
    groupingBy(DonHang::isHoanTat, counting()))
```

Các biểu thức rút gọn trên giả định có `import static java.util.stream.Collectors.*;` và được đặt làm collector của `stream.collect(...)`.

Khi áp dụng thực tế, hãy xác định **kiểu khóa**, **kiểu kết quả từng nhóm**, **yêu cầu thứ tự**, **cách xử lý nhóm vắng mặt** và **giới hạn tài nguyên**. Dùng `mapFactory` khi cần loại `Map` cụ thể; dùng `partitioningBy` khi muốn chia thành hai nhánh Boolean; dùng downstream thống kê khi không cần giữ toàn bộ bản ghi. Các lựa chọn đó giúp pipeline khai báo rõ ràng và dễ mở rộng sang xử lý dữ liệu lớn hoặc song song.
