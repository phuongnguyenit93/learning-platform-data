# Tạo các biến thể bằng BaseMultiResolutionImage (Java 9+)

## 1. Vì sao cần nhiều biến thể của cùng một hình?

Trong ứng dụng Java Desktop (AWT/Swing), một biểu tượng có thể được vẽ với kích thước logic **64 × 64** nhưng xuất hiện trên màn hình có tỷ lệ điểm ảnh **100%, 200% hoặc 300%**. Ở tỷ lệ 200%, diện tích 64 × 64 đơn vị vẽ có thể cần khoảng **128 × 128 điểm ảnh vật lý**. Nếu chương trình chỉ sở hữu ảnh raster 64 × 64 rồi phóng to lên, đường cong, chữ và biên có thể bị nhòe.

**Ảnh đa độ phân giải (multi-resolution image)** gom nhiều ảnh raster thể hiện **cùng một nội dung**, mỗi ảnh có kích thước điểm ảnh khác nhau, thành **một đối tượng `Image`**. Bộ vẽ có thể chọn biến thể phù hợp với kích thước đích và biến đổi tọa độ khi hiển thị.

Ví dụ:

```text
Cùng một biểu tượng "dấu tròn trong ô vuông":
    64 × 64 px   ──► biến thể 1×
   128 × 128 px  ──► biến thể 2×
   192 × 192 px  ──► biến thể 3×
          │
          ▼
new BaseMultiResolutionImage(icon1x, icon2x, icon3x)
          │
          ├── getResolutionVariant(64, 64)   → icon1x
          ├── getResolutionVariant(100, 120) → icon2x
          └── getResolutionVariant(160, 160) → icon3x
```

Trong Java 9 trở lên, `java.awt.image.BaseMultiResolutionImage` là một triển khai có sẵn để thực hiện việc này. API vẫn có mặt trong Java SE hiện đại, phù hợp khi bạn đang trực tiếp xử lý ảnh cho AWT/Swing hoặc một pipeline vẽ dùng `java.awt.Image`.

**Ranh giới trách nhiệm:** `BaseMultiResolutionImage` **không tự tạo** các bản 1×/2×/3×. Bạn phải chuẩn bị từng hình (đọc từ tài nguyên hoặc vẽ lại ở độ phân giải tương ứng); lớp này chỉ **tập hợp, quản lý và chọn** biến thể. Muốn tạo ảnh sắc nét ở kích thước lớn, nên xuất mỗi biến thể từ hình vector hoặc vẽ lại chi tiết ở độ phân giải đó.

## 2. Các kiểu và phương thức liên quan

| Thành phần | Vai trò |
|---|---|
| `java.awt.Image` | Lớp cha cho đối tượng ảnh; có thể truyền vào nhiều phương thức `Graphics.drawImage(...)`. |
| `java.awt.image.BufferedImage` | Ảnh bitmap lưu trong bộ nhớ, có kích thước biết trước; phù hợp để tạo từng biến thể và vẽ qua `Graphics2D`. |
| `java.awt.image.MultiResolutionImage` | Interface mô tả ảnh có nhiều biến thể; khai báo `getResolutionVariants()` và `getResolutionVariant(width, height)`. |
| `java.awt.image.AbstractMultiResolutionImage` | Lớp cơ sở cung cấp một phần hành vi `Image`, để các lớp con tự quy định nguồn biến thể. |
| `java.awt.image.BaseMultiResolutionImage` | Triển khai cụ thể sử dụng một mảng `Image` có sẵn, với thuật toán chọn biến thể rõ ràng. |
| `java.awt.Graphics2D` | Bộ vẽ 2D, có thể vẽ một `MultiResolutionImage`, tính đến kích thước đích và phép biến đổi tọa độ. |

Cây kiểu:

```text
java.awt.Image
└── AbstractMultiResolutionImage
    └── BaseMultiResolutionImage
          implements MultiResolutionImage
```

`BaseMultiResolutionImage` có từ **Java 9**, được cung cấp trong module **`java.desktop`**. Nếu viết ứng dụng có `module-info.java`, module của ứng dụng cần khai báo `requires java.desktop;`. Với chương trình Java thông thường chạy trên classpath, chỉ cần import lớp như trong ví dụ.

## 3. Chuẩn bị đúng các biến thể 1×, 2×, 3×

Giả sử một biểu tượng có kích thước thiết kế **64 × 64** trong giao diện:

| Mức hiển thị mẫu | Kích thước ảnh nên chuẩn bị | Công dụng |
|---|---:|---|
| 1× | 64 × 64 px | Phù hợp diện tích 64 × 64 pixel |
| 2× | 128 × 128 px | Phù hợp vùng 64 × 64 được đưa ra khoảng 128 × 128 pixel vật lý |
| 3× | 192 × 192 px | Phù hợp vùng hiển thị có tỷ lệ 3× |

**Nên bảo đảm các ảnh:**

1. Có cùng nội dung, hình dạng, màu sắc và bố cục; mỗi biến thể là một biểu diễn của **một hình logic**, không phải ba biểu tượng khác nhau.
2. Giữ cùng tỷ lệ khung hình (*aspect ratio*), ví dụ tất cả đều là hình vuông. Nếu hình cơ sở là 64 × 32 thì các bản 2×, 3× tương ứng thường là 128 × 64 và 192 × 96.
3. Có độ sắc nét thực sự ở kích thước mỗi bản. **Phóng đại ảnh nhỏ rồi lưu thành ảnh lớn không tạo ra chi tiết mới**.
4. Được **xếp tăng dần theo kích thước** khi chuyển vào `BaseMultiResolutionImage`: mỗi ảnh sau nên có cả chiều rộng và chiều cao lớn hơn ảnh trước.
5. Nếu cần nền trong suốt, dùng dữ liệu ảnh có alpha, ví dụ `BufferedImage.TYPE_INT_ARGB` hoặc PNG có kênh alpha.

Các ảnh có thể được tải từ ba tệp PNG do nhóm thiết kế xuất, hoặc tạo trực tiếp bằng `Graphics2D`. Bài này sử dụng cách thứ hai để ví dụ chạy được mà không phụ thuộc tài nguyên bên ngoài.

## 4. Tạo BaseMultiResolutionImage với hai constructor

### Constructor mặc định: ảnh đầu là ảnh cơ sở

```java
BufferedImage icon1x = /* ảnh 64x64 đã tạo hoặc đọc */;
BufferedImage icon2x = /* ảnh 128x128 đã tạo hoặc đọc */;
BufferedImage icon3x = /* ảnh 192x192 đã tạo hoặc đọc */;

BaseMultiResolutionImage image =
        new BaseMultiResolutionImage(icon1x, icon2x, icon3x);
```

**Đây là đoạn minh họa**, các biến ảnh phải được khởi tạo trước. Trong constructor `BaseMultiResolutionImage(Image... resolutionVariants)`:

- Đối số là các `Image` theo thứ tự đề xuất từ nhỏ đến lớn.
- **Phần tử đầu tiên** là **ảnh cơ sở (base image)**.
- `getWidth(null)` và `getHeight(null)` của wrapper trả kích thước ảnh cơ sở; ở ví dụ này là **64 × 64**.
- Mọi biến thể vẫn sẵn có để chọn qua `getResolutionVariant(...)`.

“Base image” là ảnh đại diện cho kích thước mặc định của đối tượng `Image`. Nó **không** có nghĩa phương thức chọn biến thể sẽ luôn bắt đầu từ ảnh cơ sở; thuật toán chọn vẫn kiểm tra **mảng biến thể từ đầu**.

### Constructor chỉ định ảnh cơ sở theo index

```java
BaseMultiResolutionImage image =
        new BaseMultiResolutionImage(
                1, icon1x, icon2x, icon3x);
```

Đây cũng là đoạn minh họa. Constructor `BaseMultiResolutionImage(int baseImageIndex, Image... resolutionVariants)` sử dụng **index zero-based**:

- Index `0` → base = `icon1x` (64 × 64).
- Index `1` → base = `icon2x` (128 × 128).
- Index `2` → base = `icon3x` (192 × 192).

Với index `1`, `image.getWidth(null)` trả `128`, nhưng `image.getResolutionVariant(64, 64)` **vẫn có thể chọn `icon1x`**. Chỉ định base chủ yếu ảnh hưởng kích thước mặc định và các phương thức `Image` được lớp cha ủy quyền cho ảnh cơ sở.

**Giới hạn constructor:**

- Mảng `null` hoặc không có phần tử → `IllegalArgumentException`.
- Bất kỳ phần tử ảnh nào là `null` → `NullPointerException`.
- `baseImageIndex` âm hoặc lớn hơn/bằng số lượng biến thể → `IndexOutOfBoundsException`.
- Mảng không xếp đúng thứ tự **không nhất thiết ném ngoại lệ**, nhưng có thể chọn biến thể không tối ưu.

Đừng coi việc không có ngoại lệ về thứ tự sắp xếp là bằng chứng lựa chọn ảnh đã chính xác.

## 5. Thuật toán chọn biến thể trong BaseMultiResolutionImage

Phương thức:

```java
Image candidate =
        image.getResolutionVariant(120.0, 120.0);
```

Nhận **kích thước đích tính bằng pixel**. Triển khai `BaseMultiResolutionImage` kiểm tra mảng theo đúng thứ tự đã cung cấp và trả về **ảnh đầu tiên đủ lớn cả chiều rộng lẫn chiều cao**:

```text
for (mỗi biến thể theo thứ tự đã cung cấp):
    if (width >= requestedWidth &&
        height >= requestedHeight):
        return biến thể đó
return biến thể cuối cùng
```

Đây là **giả mã giải thích**, không phải Java runnable. Ở bộ ảnh `64², 128², 192²`:

| Kích thước đích yêu cầu | Biến thể trả về | Lý do |
|---|---|---|
| 32 × 32 | 64 × 64 | Ảnh đầu tiên đã đủ lớn |
| 64 × 64 | 64 × 64 | Vừa đủ |
| 65 × 65 | 128 × 128 | 64 × 64 không đủ |
| 100 × 120 | 128 × 128 | Cả hai chiều 128 đều ≥ yêu cầu |
| 130 × 120 | 192 × 192 | Chiều rộng 130 vượt quá 128 |
| 192 × 192 | 192 × 192 | Vừa đủ |
| 300 × 300 | 192 × 192 | Không biến thể nào đủ lớn → trả **ảnh cuối** |

Hai điểm dễ nhầm:

- **Chỉ cần thiếu một chiều** là ảnh chưa đáp ứng yêu cầu; không dùng diện tích hay trung bình hai cạnh để quyết định.
- Trả về biến thể cuối khi không đủ lớn **không có nghĩa nó là ảnh đủ sắc nét**; bộ vẽ vẫn phải phóng to nếu kích thước đích lớn hơn ảnh lớn nhất.

Theo hợp đồng `MultiResolutionImage`, chiều rộng hoặc chiều cao yêu cầu **phải là giá trị hữu hạn và lớn hơn 0**. `0`, số âm, `Double.NaN` và vô cực là không hợp lệ, dẫn đến `IllegalArgumentException`.

Phương thức `getResolutionVariants()` trả danh sách các ảnh biến thể; danh sách không rỗng. Vì kiểu trả về chỉ bảo đảm một danh sách để đọc, **không phụ thuộc khả năng sửa danh sách đó** và không coi việc sửa mảng/đối tượng được lưu là cơ chế cấu hình mới.

## 6. Ví dụ Java 17+ đầy đủ: tự vẽ ba biến thể và kiểm tra thuật toán

Chương trình không yêu cầu ảnh PNG, máy chủ hay cửa sổ giao diện. Nó tạo ba `BufferedImage` với **cùng một mẫu hình**, vẽ mỗi bản **trực tiếp ở kích thước gốc**; sau đó bọc thành `BaseMultiResolutionImage` và quan sát kết quả chọn.

Tạo tệp **`ResolutionVariantsExample.java`**:

```java
import java.awt.Color;
import java.awt.Graphics2D;
import java.awt.Image;
import java.awt.RenderingHints;
import java.awt.image.BaseMultiResolutionImage;
import java.awt.image.BufferedImage;

public class ResolutionVariantsExample {

    private static BufferedImage renderIcon(int size) {
        BufferedImage result = new BufferedImage(
                size, size, BufferedImage.TYPE_INT_ARGB);
        Graphics2D g = result.createGraphics();

        try {
            g.setRenderingHint(
                    RenderingHints.KEY_ANTIALIASING,
                    RenderingHints.VALUE_ANTIALIAS_ON);

            g.setColor(new Color(25, 118, 210));
            g.fillRoundRect(0, 0, size, size,
                    size / 4, size / 4);

            g.setColor(Color.WHITE);
            g.fillOval(size / 4, size / 4,
                    size / 2, size / 2);
        } finally {
            g.dispose();
        }

        return result;
    }

    private static void show(
            BaseMultiResolutionImage icon, int w, int h) {
        Image best = icon.getResolutionVariant(w, h);
        System.out.printf(
                "%dx%d -> %dx%d%n",
                w, h, best.getWidth(null), best.getHeight(null));
    }

    public static void main(String[] args) {
        BufferedImage one = renderIcon(64);
        BufferedImage two = renderIcon(128);
        BufferedImage three = renderIcon(192);

        BaseMultiResolutionImage icon =
                new BaseMultiResolutionImage(one, two, three);

        System.out.printf(
                "base = %dx%d%n",
                icon.getWidth(null), icon.getHeight(null));
        System.out.println(
                "variants = " + icon.getResolutionVariants().size());

        show(icon, 64, 64);
        show(icon, 65, 65);
        show(icon, 100, 120);
        show(icon, 130, 120);
        show(icon, 300, 300);

        BaseMultiResolutionImage baseTwo =
                new BaseMultiResolutionImage(1, one, two, three);

        System.out.printf(
                "base index 1 = %dx%d%n",
                baseTwo.getWidth(null), baseTwo.getHeight(null));
        show(baseTwo, 64, 64);
    }
}
```

Lệnh biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 ResolutionVariantsExample.java
java ResolutionVariantsExample
```

**Stdout:**

```text
base = 64x64
variants = 3
64x64 -> 64x64
65x65 -> 128x128
100x120 -> 128x128
130x120 -> 192x192
300x300 -> 192x192
base index 1 = 128x128
64x64 -> 64x64
```

Ví dụ này đã được kiểm tra bằng JDK hiện đại với cùng thuật toán. Nó hoạt động cả trong môi trường **không có màn hình (headless)** vì chỉ tạo và vẽ lên `BufferedImage` trong bộ nhớ, không tạo cửa sổ AWT/Swing.

### Giải thích từng bước

1. `renderIcon(64)`, `renderIcon(128)` và `renderIcon(192)` đều **vẽ lại cùng mẫu** hình vuông xanh và hình tròn trắng; như vậy ba bitmap có chi tiết hình học được dựng trực tiếp theo độ phân giải.
2. `BufferedImage.TYPE_INT_ARGB` hỗ trợ alpha; phù hợp với biểu tượng có nền trong suốt nếu mẫu hình của bạn cần.
3. `RenderingHints.KEY_ANTIALIASING` yêu cầu đường cong mượt hơn lúc vẽ các shape. Nó **không** thay thế việc cung cấp biến thể độ phân giải lớn.
4. `Graphics2D.dispose()` giải phóng tài nguyên của đối tượng vẽ; không cần đóng `BufferedImage` như stream.
5. `getResolutionVariants().size()` bằng `3` vì wrapper chứa ba hình.
6. `baseTwo` có ảnh cơ sở 128 × 128, nhưng `getResolutionVariant(64, 64)` vẫn chọn phần tử đầu 64 × 64. Điều này chứng minh **base index và thứ tự tìm biến thể là hai vấn đề riêng**.

## 7. Đưa ảnh đa độ phân giải vào AWT/Swing

Đối tượng `BaseMultiResolutionImage` cũng là một `Image`, do đó có thể truyền vào API vẽ hình ảnh:

```java
// MẢNH MÃ: icon là BaseMultiResolutionImage đã tạo ở mục 6.
// g là Graphics được cung cấp bởi cơ chế vẽ AWT/Swing.
g.drawImage(icon, 0, 0, 64, 64, null);
```

Đối với những đường vẽ hỗ trợ `MultiResolutionImage`, các overload `Graphics.drawImage(...)` sẽ tham khảo biến thể thích hợp cho lần vẽ. Khi có phép biến đổi tọa độ của thiết bị (**HiDPI**), kích thước đích thực tế có thể lớn hơn số đơn vị vẽ mà lập trình viên nhìn thấy.

Ví dụ: kích thước logic 64 × 64 được vẽ trên ngữ cảnh có `Graphics2D.scale(2, 2)` thì vùng đích có thể tương ứng khoảng 128 × 128 pixel của bitmap. Hình 2× có cơ hội được chọn, tránh phải phóng to hình 1×. **Việc chọn biến thể thực tế phụ thuộc lệnh vẽ, biến đổi tọa độ và pipeline đồ họa**; không suy ra rằng mọi môi trường đều chọn cùng ảnh chỉ từ tỷ lệ DPI được báo.

Một ví dụ vẽ thử lên ảnh đích trong bộ nhớ:

```java
// MẢNH MÃ, đặt trong phương thức có biến icon của mục 6.
BufferedImage canvas = new BufferedImage(
        128, 128, BufferedImage.TYPE_INT_ARGB);
Graphics2D g = canvas.createGraphics();

try {
    g.scale(2.0, 2.0);
    g.drawImage(icon, 0, 0, 64, 64, null);
} finally {
    g.dispose();
}
```

Đây là đoạn minh họa tạo ảnh 128 × 128 trong bộ nhớ, không bật cửa sổ. Kết quả có thể được kiểm tra trực quan hoặc lưu thành PNG bằng `ImageIO.write(canvas, "png", outputFile)` nếu người gọi cung cấp `outputFile`.

### Swing với ImageIcon

Trong ứng dụng Swing, có thể dùng cùng đối tượng ảnh để tạo biểu tượng:

```java
// MẢNH MÃ: image là BaseMultiResolutionImage có base 64x64.
ImageIcon icon = new ImageIcon(image);
JLabel label = new JLabel(icon);
```

Cần import `javax.swing.ImageIcon` và `javax.swing.JLabel`. Trong hệ thống hiển thị tương thích, đường vẽ `ImageIcon`/AWT có thể sử dụng biến thể độ phân giải cao khi tỷ lệ render yêu cầu. Tuy vậy, kích thước thành phần và bố cục thường được tính theo **ảnh cơ sở**, nên hãy chọn base image có kích thước logic mà bạn muốn hiển thị. Nếu bạn tự vẽ bằng `paintComponent`, tuân thủ vòng đời vẽ của Swing và thực hiện thay đổi giao diện trên **Event Dispatch Thread (EDT)**.

**Đừng gọi `getResolutionVariant(128, 128)` rồi luôn gắn ảnh trả về vào `JLabel` nếu mục tiêu là tự thích nghi khi chuyển cửa sổ giữa các màn hình DPI khác nhau.** Hành động đó biến một bản cụ thể thành ảnh thông thường; giữ wrapper `BaseMultiResolutionImage` mới cho phép bộ vẽ chọn theo lần render.

## 8. Tạo biến thể từ các tệp PNG có sẵn

Trong dự án thực tế, nhóm thiết kế có thể xuất những tệp:

```text
src/main/resources/icons/
├── action.png       (64x64)
├── action@2x.png    (128x128)
└── action@3x.png    (192x192)
```

Đọc ảnh từ resource trong classpath rồi ghép:

```java
// MẢNH MÃ: giả định tồn tại ba resource ở classpath.
BufferedImage a = ImageIO.read(
        MyView.class.getResource("/icons/action.png"));
BufferedImage b = ImageIO.read(
        MyView.class.getResource("/icons/action@2x.png"));
BufferedImage c = ImageIO.read(
        MyView.class.getResource("/icons/action@3x.png"));

BaseMultiResolutionImage image =
        new BaseMultiResolutionImage(a, b, c);
```

Đây là **mảnh mã**, trong đó `MyView.class` đại diện cho lớp thật của ứng dụng; cần import `javax.imageio.ImageIO`, `java.awt.image.BufferedImage` và `java.awt.image.BaseMultiResolutionImage`, đồng thời xử lý `IOException` và resource không tồn tại. Trong ứng dụng dùng module, resource còn phụ thuộc quy tắc đóng gói và khả năng truy cập module.

**Kiểm tra dữ liệu khi nạp:** Nếu `getResource(...)` trả `null`, phải báo lỗi đường dẫn rõ ràng trước khi đọc. `ImageIO.read(...)` cũng có thể trả `null` nếu không có decoder phù hợp. Một trong các ảnh trở thành `null` sẽ khiến constructor `BaseMultiResolutionImage` ném `NullPointerException`; không để trường hợp này xảy ra âm thầm.

Ngoài ra, không bắt buộc mọi biến thể phải là `BufferedImage`. Constructor nhận các `Image` nói chung, nhưng dùng ảnh đã nạp đầy đủ và có kích thước biết trước giúp việc lựa chọn, hiển thị và kiểm thử ít bất ngờ hơn.

## 9. Trường hợp cần tự chọn biến thể

Trong code AWT/Swing thông thường, bạn có thể đưa wrapper vào `Graphics.drawImage` để pipeline xử lý. Tuy nhiên, khi xuất ảnh, tạo thumbnail ở một kích thước xác định, hoặc chuyển cho thư viện **chỉ hiểu `BufferedImage`**, việc tự chọn biến thể có ích:

```java
// MẢNH MÃ: icon là BaseMultiResolutionImage đã chuẩn bị.
Image selected = icon.getResolutionVariant(150, 150);

if (!(selected instanceof BufferedImage selectedBitmap)) {
    throw new IllegalStateException(
            "Biến thể đã chọn không phải BufferedImage");
}

// selectedBitmap có thể dùng trong pipeline cần BufferedImage.
```

Dùng cú pháp `instanceof` binding variable như trên được Java 17 hỗ trợ. Giá trị `150 × 150` sẽ chọn ảnh `192 × 192` trong ví dụ trước. Hãy kiểm tra hợp đồng kích thước đầu vào: chúng là **pixel đích cần biểu diễn**, không phải số lần nhân DPI một cách mặc định.

Khi mục tiêu xuất tệp PNG đúng **150 × 150**, bạn vẫn cần một bước **render/scale** để tạo bitmap có kích thước chính xác; phương thức `getResolutionVariant(150, 150)` chỉ **trả ảnh nguồn** 192 × 192, không tự trả bitmap mới 150 × 150.

## 10. Những lỗi thường gặp và cách khắc phục

| Lỗi | Hậu quả và cách giải quyết |
|---|---|
| Chỉ truyền một bitmap phóng to từ ảnh 1× | Ảnh độ phân giải lớn không có thêm chi tiết; nên dựng lại từ vector/shape hoặc dùng tài nguyên xuất ở kích thước gốc. |
| Đặt ảnh 3× trước ảnh 1× | Thuật toán chọn **phần tử đầu đủ lớn**; ảnh 3× có thể bị chọn cả ở yêu cầu nhỏ. Sắp xếp ảnh từ nhỏ đến lớn theo cả hai chiều. |
| Chỉ một chiều đủ lớn | Ví dụ 128 × 64 không thể đáp ứng yêu cầu 100 × 100; cần cả chiều rộng và chiều cao phù hợp. |
| Dùng `baseImageIndex` như chỉ số bắt đầu duyệt | Base index chỉ chọn ảnh đại diện cho kích thước mặc định; quá trình chọn biến thể vẫn xét các phần tử theo thứ tự mảng. |
| Không có ảnh nào đủ lớn, tưởng trả `null` | `BaseMultiResolutionImage` trả biến thể **cuối**, nên ảnh có thể bị phóng lớn khi render. |
| Truyền `null`, mảng rỗng, hoặc index ngoài phạm vi | Constructor ném `IllegalArgumentException`, `NullPointerException` hoặc `IndexOutOfBoundsException` tùy trường hợp. |
| Gọi `getResolutionVariant(0, 0)` hay truyền `NaN` | Kích thước yêu cầu không hợp lệ; dùng số hữu hạn và lớn hơn 0. |
| Gọi `image.getGraphics()` để sửa wrapper | `AbstractMultiResolutionImage.getGraphics()` ném `UnsupportedOperationException`. Hãy vẽ vào từng `BufferedImage` trước khi gói. |
| Muốn wrapper tự sinh các bản 2×, 3× | Lớp này không tự tạo bitmap mới; bạn phải cung cấp các `Image` riêng. |
| Thay đổi bitmap biến thể sau khi dựng wrapper | Wrapper tham chiếu tới các ảnh; thay đổi nội dung biến thể có thể ảnh hưởng kết quả về sau. Chuẩn bị ảnh xong trước khi sử dụng chung. |
| Tự lấy một biến thể rồi cố định vào giao diện | Mất khả năng tự chọn khi quy mô vẽ/HiDPI thay đổi; nên truyền wrapper cho pipeline hỗ trợ. |
| Đặt nhiều ảnh khác tỷ lệ khung hình | Có thể bị co kéo/méo khi vẽ; giữ nội dung và tỷ lệ thống nhất. |
| Mỗi biểu tượng có quá nhiều bản rất lớn | Tốn bộ nhớ và thời gian nạp; ưu tiên vài mức phù hợp với thiết bị thực tế, tái sử dụng đối tượng ảnh nếu có thể. |

### Lưu ý về hiệu năng và chất lượng

Một `BufferedImage` kiểu `TYPE_INT_ARGB` lưu các pixel màu 32 bit; phần dữ liệu pixel thô của bộ ba ảnh 64², 128², 192² chiếm khoảng:

```text
(64² + 128² + 192²) × 4 byte
= (4096 + 16384 + 36864) × 4
= 229376 byte
≈ 224 KiB
```

Đây chỉ là **kích thước dữ liệu pixel thô**, chưa bao gồm header, metadata, đối tượng Java và bộ nhớ do pipeline đồ họa quản lý. Kích thước ảnh tăng theo **bình phương tỷ lệ**, vì vậy chỉ tạo những bản độ phân giải thực sự hữu ích. Có thể dùng cache dùng chung cho các icon đã nạp khi giao diện có nhiều thành phần sử dụng cùng tài nguyên.

## 11. Tự kiểm tra kiến thức

1. **Tại sao 64 × 64 không đủ sắc nét trên màn hình 200%?** Vì vùng vẽ có thể cần khoảng 128 × 128 pixel vật lý; phóng to bitmap 1× có thể làm mất độ rõ.
2. **`BaseMultiResolutionImage` có tự sinh ảnh 2× không?** Không. Nó chỉ gom và chọn các `Image` đã được tạo/cung cấp.
3. **Ảnh nào được chọn ở yêu cầu 70 × 60 khi có ảnh 64², 128², 192²?** 128 × 128; ảnh 64 × 64 thiếu chiều rộng.
4. **Nếu yêu cầu 400 × 400 thì sao?** Chọn phần tử cuối 192 × 192; bộ vẽ phải phóng to nếu muốn hiển thị lớn hơn.
5. **Nếu dùng `new BaseMultiResolutionImage(1, a64, b128, c192)`, `getWidth(null)` trả bao nhiêu?** 128, vì base image là `b128`.
6. **Trong trường hợp trên, `getResolutionVariant(64,64)` trả ảnh nào?** `a64`, vì thuật toán lựa chọn không bắt đầu từ base index.
7. **Khi nào dùng `Graphics2D.drawImage(wrapper, ...)`?** Khi render trong đường vẽ hỗ trợ `MultiResolutionImage`, muốn môi trường tự chọn biến thể phù hợp.
8. **Vì sao không sửa wrapper bằng `getGraphics()`?** Nó không phải canvas bitmap; phương thức được lớp cha triển khai để ném `UnsupportedOperationException`.
9. **Muốn PNG xuất ra đúng 150 × 150 thì `getResolutionVariant(150,150)` đã đủ chưa?** Chưa. Nó lấy ảnh nguồn phù hợp, còn muốn đúng 150 × 150 phải render hoặc scale sang bitmap đích.

## Tài liệu API hiện hành

- [`BaseMultiResolutionImage` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/java/awt/image/BaseMultiResolutionImage.html)
- [`MultiResolutionImage` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/java/awt/image/MultiResolutionImage.html)
- [`AbstractMultiResolutionImage` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/java/awt/image/AbstractMultiResolutionImage.html)
- [`Graphics2D` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/java/awt/Graphics2D.html)
- [`BufferedImage` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/java/awt/image/BufferedImage.html)
- [JEP 251 — Multi-Resolution Images](https://openjdk.org/jeps/251)
