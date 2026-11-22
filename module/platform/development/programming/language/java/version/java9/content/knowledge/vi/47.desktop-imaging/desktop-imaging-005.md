# Metadata TIFF và kiểm tra bộ đọc, bộ ghi hỗ trợ (Java 9+)

## Mục tiêu

Từ Java 9, JDK có bộ đọc/ghi TIFF qua Java Image I/O và các API công khai trong `javax.imageio.plugins.tiff`, thuộc mô-đun `java.desktop`. Các API này vẫn hiện hành trên JDK hiện đại. Bài học giải thích cấu trúc TIFF, cách kiểm tra bộ đọc/bộ ghi, đọc và chỉnh metadata, kiểm tra file nhiều trang, tính tương thích của tag/nén và quy trình kiểm thử thực tế.

Sau bài này, bạn có thể xác minh đúng runtime có TIFF reader/writer không; phân biệt “provider đăng ký TIFF” với “có thể đọc/ghi file cụ thể”; truy cập `TIFFDirectory`, `TIFFTag`, `TIFFField`; tạo TIFF có `ImageDescription`; và tránh làm mất Exif/GPS, orientation hay thông tin của các trang khác.

## 1. TIFF và metadata được tổ chức thế nào?

TIFF (Tagged Image File Format) có thể chứa một hoặc nhiều **Image File Directory (IFD)**. Mỗi IFD chứa các **entry** gắn với tag number, type, count và value, mô tả dữ liệu của một ảnh/trang và đôi khi trỏ tới IFD khác. Dữ liệu raster có thể nằm theo strip/tile và có nén.

```text
TIFF
├── Header / byte order
├── IFD 0
│   ├── ImageWidth, ImageLength
│   ├── Compression, PhotometricInterpretation
│   ├── Orientation, XResolution, YResolution
│   ├── ImageDescription
│   └── Strip/Tile offsets + dữ liệu ảnh
├── IFD 1, IFD 2... nếu có nhiều trang
└── Sub-IFD/extension nếu có Exif, GPS...
```

Các tag phổ biến trong `BaselineTIFFTagSet`:

| Tag number | Hằng Java | Nội dung |
| --- | --- | --- |
| 256 / 257 | `TAG_IMAGE_WIDTH` / `TAG_IMAGE_LENGTH` | Kích thước ảnh |
| 259 | `TAG_COMPRESSION` | Kiểu nén dữ liệu ảnh |
| 270 | `TAG_IMAGE_DESCRIPTION` | Chuỗi mô tả TIFF ASCII |
| 274 | `TAG_ORIENTATION` | Hướng hiển thị |
| 282 / 283 | `TAG_X_RESOLUTION` / `TAG_Y_RESOLUTION` | Độ phân giải kiểu rational |
| 296 | `TAG_RESOLUTION_UNIT` | Đơn vị độ phân giải |

Metadata và raster có quan hệ nhưng là hai việc khác nhau: đọc `Orientation` không có nghĩa thư viện đã xoay pixel; sửa `ImageWidth` trong metadata không thay đổi ảnh. Một file TIFF có thể hợp lệ nhưng cần kiểu nén, pixel layout hoặc extension mà reader hiện tại không hỗ trợ.

## 2. Các API hiện hành nên dùng

| API | Công dụng |
| --- | --- |
| `ImageIO` | Khám phá Image I/O plug-in, tạo stream, tìm reader/writer |
| `ImageReader` | Đọc kích thước, số trang, `IIOMetadata` và pixel từng trang |
| `ImageWriter` | Ghi một ảnh hoặc chuỗi ảnh, gắn metadata |
| `ImageTypeSpecifier` | Mô tả kiểu ảnh để kiểm tra khả năng writer |
| `ImageReadParam` / `ImageWriteParam` | Cấu hình vùng đọc, kiểu nén, chất lượng… nếu provider hỗ trợ |
| `IIOMetadata` | Metadata ở dạng native của provider hoặc dạng chung |
| `TIFFDirectory` | Một IFD, cho phép đọc/ghi các `TIFFField` |
| `TIFFField` | Tag, type, count và dữ liệu của một field |
| `TIFFTag` / `TIFFTagSet` | Định nghĩa tag và tập tag |
| `BaselineTIFFTagSet` | Tag TIFF cơ bản |
| `ExifTIFFTagSet` / `ExifGPSTagSet` / `GeoTIFFTagSet` | Các tập tag mở rộng |
| `TIFFImageReadParam` | Tùy chọn tag set, đọc tag chưa biết trong TIFF plugin tương thích |

`javax.imageio.plugins.tiff` bắt đầu bằng `javax` nhưng **không phải API lỗi thời**; dùng các class công khai này thay vì phụ thuộc vào class triển khai nội bộ của JDK. Chương trình Java 17+ chạy classpath thông thường không cần thêm thư viện ngoài. Nếu dùng named module, khai báo `requires java.desktop;`.

## 3. Phát hiện khả năng đọc/ghi TIFF

Các API khám phá provider:

```java
Iterator<ImageReader> readers =
        ImageIO.getImageReadersByFormatName("TIFF");
Iterator<ImageWriter> writers =
        ImageIO.getImageWritersByFormatName("TIFF");
```

Hai lệnh này **chỉ phát hiện provider đăng ký tên định dạng**, chưa chứng minh provider giải mã được bất kỳ biến thể TIFF nào.

Khi cần xác minh sâu hơn:

- **File cụ thể:** tạo `ImageInputStream` và gọi `ImageIO.getImageReaders(input)` để chọn reader dựa trên dữ liệu thực; đuôi `.tif` hoặc `.tiff` không đủ.
- **Kiểu raster:** dùng `ImageIO.getImageWriters(imageType, "TIFF")` hoặc `ImageWriterSpi.canEncodeImage(imageType)`.
- **Nén:** hỏi `ImageWriteParam.canWriteCompressed()`; khi thích hợp chuyển sang `ImageWriteParam.MODE_EXPLICIT` và lấy `getCompressionTypes()`.
- **Multi-page:** xem `writer.canWriteSequence()`; đọc nhiều trang bằng các chỉ số `reader.getImageMetadata(i)`, `getWidth(i)`, `getHeight(i)`.
- **Metadata:** kiểm tra `reader.getImageMetadata(i)`, `writer.getDefaultImageMetadata(...)` và các tên metadata format được công bố.

Một tên nén xuất hiện trong `getCompressionTypes()` cũng chưa có nghĩa writer hỗ trợ tên nén đó với **mọi** pixel type. Đặc biệt nén fax gắn với ảnh 1-bit; kiểu nén JPEG-in-TIFF lại có giới hạn tương thích riêng. Kiểm chứng bằng sample tương ứng và đọc lại output.

### Ví dụ Java 17+: khảo sát provider

Lưu thành `TiffSupportCheck.java`:

```java
import java.awt.image.BufferedImage;
import java.util.Arrays;
import java.util.Iterator;
import javax.imageio.ImageIO;
import javax.imageio.ImageReader;
import javax.imageio.ImageTypeSpecifier;
import javax.imageio.ImageWriteParam;
import javax.imageio.ImageWriter;

public class TiffSupportCheck {
    public static void main(String[] args) throws Exception {
        Iterator<ImageReader> readers =
                ImageIO.getImageReadersByFormatName("TIFF");
        boolean hasReader = false;
        while (readers.hasNext()) {
            ImageReader reader = readers.next();
            try {
                hasReader = true;
                System.out.println("reader=" + reader.getClass().getName());
            } finally {
                reader.dispose();
            }
        }
        System.out.println("readerAvailable=" + hasReader);

        Iterator<ImageWriter> writers =
                ImageIO.getImageWritersByFormatName("TIFF");
        boolean hasWriter = false;
        while (writers.hasNext()) {
            ImageWriter writer = writers.next();
            try {
                hasWriter = true;
                System.out.println("writer=" + writer.getClass().getName());

                ImageTypeSpecifier rgb =
                        ImageTypeSpecifier.createFromBufferedImageType(
                                BufferedImage.TYPE_INT_RGB);
                boolean rgbSupported =
                        writer.getOriginatingProvider() != null
                        && writer.getOriginatingProvider().canEncodeImage(rgb);
                System.out.println("RGB supported=" + rgbSupported);
                System.out.println("multi-page="
                        + writer.canWriteSequence());

                ImageWriteParam param = writer.getDefaultWriteParam();
                if (param.canWriteCompressed()) {
                    param.setCompressionMode(ImageWriteParam.MODE_EXPLICIT);
                    System.out.println("compression types="
                            + Arrays.toString(param.getCompressionTypes()));
                } else {
                    System.out.println("compression not configurable");
                }
            } finally {
                writer.dispose();
            }
        }
        System.out.println("writerAvailable=" + hasWriter);
    }
}
```

Chạy:

```sh
javac --release 17 -encoding UTF-8 TiffSupportCheck.java
java TiffSupportCheck
```

Output phụ thuộc provider được đăng ký trên máy nên không có danh sách cố định. Đã thử tương đương trên OpenJDK 24: reader/writer TIFF tích hợp đều hiện diện; writer công bố hỗ trợ kiểu RGB, ghi sequence và có nhiều kiểu nén. Không dựa vào tên class implementation hoặc thứ tự/tên compression từ một máy để cấu hình production.

## 4. Dữ liệu TIFF native metadata và tag

`ImageReader.getImageMetadata(0)` trả một `IIOMetadata` của trang 0 khi reader hỗ trợ metadata, hoặc có thể `null`. `TIFFDirectory.createFromMetadata(metadata)` chuyển đối tượng metadata TIFF tương thích thành IFD. `TIFFDirectory.getTIFFField(number)` lấy field theo tag; nếu tag không có, kết quả là `null`.

```java
// Minh họa: reader đã setInput(...) vào TIFF và còn mở.
IIOMetadata metadata = reader.getImageMetadata(0);
if (metadata != null) {
    TIFFDirectory directory = TIFFDirectory.createFromMetadata(metadata);
    TIFFField description = directory.getTIFFField(
            BaselineTIFFTagSet.TAG_IMAGE_DESCRIPTION);
    if (description != null
            && description.getType() == TIFFTag.TIFF_ASCII
            && description.getCount() > 0) {
        System.out.println(description.getAsString(0));
    }
}
```

Đoạn này cần `reader` đã được tạo đúng và import `javax.imageio.metadata.IIOMetadata` cùng các class `javax.imageio.plugins.tiff`.

Những điểm quan trọng:

- Một field có `getTagNumber()`, `getType()`, `getCount()` và dữ liệu. Dùng `getAsString` cho TIFF ASCII, `getAsInt` cho số phù hợp, `getAsRational` cho giá trị phân số; kiểm tra type/count trước.
- `TIFFDirectory.getTIFFFields()` chỉ trả các field của directory đó. Tag Exif/GPS có thể nằm trong sub-IFD được trỏ từ field cha, cần truy cập cấu trúc tương ứng.
- Đừng in toàn bộ dữ liệu tag có kích thước lớn hoặc dữ liệu nhị phân không tin cậy ra log.
- `TIFFDirectory.createFromMetadata` yêu cầu một metadata format tương thích với TIFF Image I/O plugin. Nếu chuyển metadata từ provider không tương thích, có thể gặp `IllegalArgumentException` hoặc `IIOInvalidTreeException`.

Hai tên metadata format cần nhận biết:

| Metadata format | Ý nghĩa |
| --- | --- |
| `javax_imageio_tiff_image_1.0` | Native TIFF metadata, có cấu trúc `TIFFIFD` và `TIFFField` |
| `javax_imageio_1.0` | Dạng chuẩn chung Image I/O, không biểu diễn lossless mọi trường riêng của TIFF |

Một `TIFFTagSet` cho biết cách diễn giải tag, **không bảo đảm** tất cả TIFF extension đều có thể đọc/ghi. Ví dụ API public có `GeoTIFFTagSet` và `ExifGPSTagSet`, nhưng một reader cụ thể vẫn có thể không hỗ trợ biến thể của file bạn đang xử lý.

## 5. Ví dụ Java chạy hoàn chỉnh: ghi metadata, đọc lại TIFF trong bộ nhớ

Ví dụ này tạo một TIFF RGB 2 × 1, gắn tag `ImageDescription`, dùng chính bytes đã ghi để đọc lại metadata, kích thước, số trang và giá trị pixel. Không yêu cầu file TIFF đầu vào và không cần thư viện ngoài.

Lưu `TiffMetadataRoundTrip.java`:

```java
import java.awt.image.BufferedImage;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.util.Iterator;
import javax.imageio.IIOImage;
import javax.imageio.ImageIO;
import javax.imageio.ImageReader;
import javax.imageio.ImageTypeSpecifier;
import javax.imageio.ImageWriteParam;
import javax.imageio.ImageWriter;
import javax.imageio.metadata.IIOMetadata;
import javax.imageio.plugins.tiff.BaselineTIFFTagSet;
import javax.imageio.plugins.tiff.TIFFDirectory;
import javax.imageio.plugins.tiff.TIFFField;
import javax.imageio.plugins.tiff.TIFFTag;
import javax.imageio.stream.ImageInputStream;
import javax.imageio.stream.ImageOutputStream;

public class TiffMetadataRoundTrip {
    public static void main(String[] args) throws Exception {
        Iterator<ImageReader> knownReaders =
                ImageIO.getImageReadersByFormatName("TIFF");
        Iterator<ImageWriter> knownWriters =
                ImageIO.getImageWritersByFormatName("TIFF");
        if (!knownReaders.hasNext() || !knownWriters.hasNext()) {
            System.out.println("TIFF reader/writer not available");
            return;
        }
        ImageWriter writer = knownWriters.next();

        BufferedImage image =
                new BufferedImage(2, 1, BufferedImage.TYPE_INT_RGB);
        image.setRGB(0, 0, 0x00AA22);

        ImageWriteParam param = writer.getDefaultWriteParam();
        IIOMetadata defaults = writer.getDefaultImageMetadata(
                ImageTypeSpecifier.createFromRenderedImage(image), param);
        TIFFDirectory directory =
                TIFFDirectory.createFromMetadata(defaults);

        TIFFTag descriptionTag = BaselineTIFFTagSet.getInstance()
                .getTag(BaselineTIFFTagSet.TAG_IMAGE_DESCRIPTION);
        directory.addTIFFField(new TIFFField(
                descriptionTag, TIFFTag.TIFF_ASCII, 1,
                new String[]{"Demo TIFF"}));

        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try {
            try (ImageOutputStream output =
                    ImageIO.createImageOutputStream(buffer)) {
                writer.setOutput(output);
                writer.write(null,
                        new IIOImage(image, null, directory.getAsMetadata()),
                        param);
            }
        } finally {
            writer.dispose();
        }

        try (ImageInputStream input =
                ImageIO.createImageInputStream(
                        new ByteArrayInputStream(buffer.toByteArray()))) {
            Iterator<ImageReader> candidates = ImageIO.getImageReaders(input);
            if (!candidates.hasNext()) {
                throw new IOException("No reader accepts generated TIFF");
            }
            ImageReader reader = candidates.next();
            try {
                reader.setInput(input);
                TIFFDirectory parsed = TIFFDirectory.createFromMetadata(
                        reader.getImageMetadata(0));
                TIFFField description = parsed.getTIFFField(
                        BaselineTIFFTagSet.TAG_IMAGE_DESCRIPTION);

                System.out.println("size="
                        + reader.getWidth(0) + "x" + reader.getHeight(0));
                System.out.println("description="
                        + (description == null ? "(missing)"
                                : description.getAsString(0)));
                System.out.println("pages=" + reader.getNumImages(true));
                System.out.println("pixelOk="
                        + (reader.read(0).getRGB(0, 0)
                                == image.getRGB(0, 0)));
            } finally {
                reader.dispose();
            }
        }
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```sh
javac --release 17 -encoding UTF-8 TiffMetadataRoundTrip.java
java TiffMetadataRoundTrip
```

Đầu ra đã kiểm chứng trên OpenJDK 24 có TIFF reader/writer tích hợp:

```text
size=2x1
description=Demo TIFF
pages=1
pixelOk=true
```

Phân tích: `getDefaultImageMetadata(...)` lấy metadata tương thích từ writer đã chọn; `TIFFDirectory.addTIFFField(...)` thêm description vào IFD; `getAsMetadata()` chuyển về metadata để đưa cho `writer.write(...)`. Sau đó, reader được chọn từ **bytes thật** và metadata/pixel được kiểm tra lại, nhờ vậy thấy được cả thành công của ghi và đọc.

`TIFFTag.TIFF_ASCII` dành cho dữ liệu ASCII. Ví dụ dùng `"Demo TIFF"` thay vì chuỗi Unicode tiếng Việt. Không ghi text Unicode không có quy ước vào field TIFF ASCII rồi mặc định các phần mềm khác sẽ hiển thị đúng; phải xác định encoding/chuẩn metadata được hai phía hỗ trợ.

## 6. Chương trình đọc metadata từ file thực tế

Để đọc một file TIFF thật, tạo `ImageInputStream`, chọn reader bằng `ImageIO.getImageReaders(input)`, kiểm tra format, sau đó lấy `reader.getImageMetadata(i)` và field theo từng trang.

Lưu `TiffInspector.java`:

```java
import java.io.File;
import java.io.IOException;
import java.util.Arrays;
import java.util.Iterator;
import javax.imageio.ImageIO;
import javax.imageio.ImageReader;
import javax.imageio.metadata.IIOMetadata;
import javax.imageio.plugins.tiff.BaselineTIFFTagSet;
import javax.imageio.plugins.tiff.TIFFDirectory;
import javax.imageio.plugins.tiff.TIFFField;
import javax.imageio.stream.ImageInputStream;

public class TiffInspector {
    private static void printField(TIFFDirectory dir, int tagNumber) {
        TIFFField f = dir.getTIFFField(tagNumber);
        if (f != null && f.getCount() > 0) {
            System.out.println("  " + f.getTag().getName()
                    + "=" + f.getValueAsString(0));
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.out.println("Usage: java TiffInspector <path-to-tiff>");
            return;
        }
        File file = new File(args[0]);
        if (!file.isFile()) {
            throw new IOException("File not found: " + file);
        }

        try (ImageInputStream input = ImageIO.createImageInputStream(file)) {
            if (input == null) {
                throw new IOException("Cannot open image input");
            }
            Iterator<ImageReader> candidates = ImageIO.getImageReaders(input);
            if (!candidates.hasNext()) {
                throw new IOException("No reader accepts file");
            }
            ImageReader reader = candidates.next();

            try {
                reader.setInput(input, false, false);
                String format = reader.getFormatName();
                if (!format.equalsIgnoreCase("TIFF")
                        && !format.equalsIgnoreCase("TIF")) {
                    throw new IOException("Not TIFF: " + format);
                }

                int pages = reader.getNumImages(true);
                System.out.println("reader=" + reader.getClass().getName());
                System.out.println("pages=" + pages);
                for (int i = 0; i < Math.min(pages, 3); i++) {
                    System.out.println("page=" + i + " size="
                            + reader.getWidth(i) + "x" + reader.getHeight(i));

                    IIOMetadata meta = reader.getImageMetadata(i);
                    if (meta == null) {
                        System.out.println("  metadata unavailable");
                        continue;
                    }
                    String[] names = meta.getMetadataFormatNames();
                    boolean nativeTiff = names != null
                            && Arrays.asList(names).contains(
                                    "javax_imageio_tiff_image_1.0");
                    if (!nativeTiff) {
                        System.out.println("  native TIFF metadata unavailable");
                        continue;
                    }

                    TIFFDirectory dir = TIFFDirectory.createFromMetadata(meta);
                    printField(dir, BaselineTIFFTagSet.TAG_IMAGE_DESCRIPTION);
                    printField(dir, BaselineTIFFTagSet.TAG_ORIENTATION);
                    printField(dir, BaselineTIFFTagSet.TAG_X_RESOLUTION);
                    printField(dir, BaselineTIFFTagSet.TAG_Y_RESOLUTION);
                    printField(dir, BaselineTIFFTagSet.TAG_RESOLUTION_UNIT);
                }
            } finally {
                reader.dispose();
            }
        }
    }
}
```

Chạy với file TIFF đã có:

```sh
javac --release 17 -encoding UTF-8 TiffInspector.java
java TiffInspector "scan.tif"
```

Output của chương trình này thay đổi theo file/provider nên không công bố một stdout giả định. Với file nhiều trang, `getNumImages(true)` có thể phải quét toàn bộ file; chương trình giới hạn **hiển thị** ba trang đầu nhưng việc đếm trang vẫn có chi phí. Do đó dùng ví dụ này trên file đã kiểm soát; với upload hoặc file lớn phải giới hạn kích thước/độ phức tạp ngay trước bước đọc.

Chỉ lấy `reader.getImageMetadata(i)` thường không cần giải mã mọi pixel, trong khi `reader.read(i)` sẽ giải mã ảnh tương ứng. `ImageIO.read(file)` tiện cho một `BufferedImage` nhưng **không phù hợp khi cần xử lý đầy đủ metadata và TIFF nhiều trang**.

## 7. Sửa metadata mà không làm hỏng ảnh

Có thể chuyển `IIOMetadata` sang `TIFFDirectory`, thay một field được phép rồi chuyển lại:

```java
// Mảnh minh họa: biến metadata là IIOMetadata TIFF tương thích.
TIFFDirectory dir = TIFFDirectory.createFromMetadata(metadata);
dir.removeTIFFField(BaselineTIFFTagSet.TAG_IMAGE_DESCRIPTION);

TIFFTag tag = BaselineTIFFTagSet.getInstance()
        .getTag(BaselineTIFFTagSet.TAG_IMAGE_DESCRIPTION);
dir.addTIFFField(new TIFFField(
        tag, TIFFTag.TIFF_ASCII, 1, new String[]{"Checked"}));

IIOMetadata updatedMetadata = dir.getAsMetadata();
```

Đoạn này cần import `javax.imageio.metadata.IIOMetadata` và `javax.imageio.plugins.tiff.*`. `updatedMetadata` mới là đối tượng trong bộ nhớ; nó cần được đưa vào `IIOImage` khi gọi writer thì mới lưu ra TIFF.

**Các nguyên tắc phải kiểm tra:**

1. **Tag và kiểu dữ liệu:** không tự gán tag với data type/count sai. `TIFF_ASCII` khác `TIFF_SHORT`, `TIFF_LONG`, `TIFF_RATIONAL` và dữ liệu sub-IFD.
2. **Tag gắn với raster:** khi resize hoặc thay kiểu nén/strip/tile, writer phải quản lý lại chiều rộng, chiều cao, offsets, byte counts và các field cấu trúc. Không chép nguyên tag cấu trúc từ ảnh cũ một cách mù quáng.
3. **Dữ liệu riêng:** metadata ở dạng `javax_imageio_1.0` là biểu diễn chung, có thể bỏ mất Exif/GeoTIFF/tag riêng. Nếu những tag này quan trọng, phải có đường chuyển TIFF native phù hợp và kiểm thử.
4. **Nhiều trang:** mỗi trang có IFD riêng; sửa trang 0 không tự đổi metadata các trang còn lại.
5. **Orientation:** thay orientation không xoay pixel; nếu đã xoay raster thật cần cập nhật metadata phù hợp để tránh ảnh bị xoay hai lần.
6. **Resolution:** `XResolution` và `YResolution` là rational; phải xem `ResolutionUnit` để biết đơn vị.
7. **Exif/GPS:** có thể chứa thông tin riêng tư; xác định chính sách giữ/xóa trước khi chia sẻ file.

Luôn ghi ra file mới hoặc vị trí tạm có kiểm tra, sau đó **mở lại thành phẩm và so sánh tag/count/type/value cần giữ**. Việc `writer.write` không báo lỗi chưa chứng minh metadata đã được bảo toàn.

## 8. TIFF nhiều trang và các phần mở rộng

Với nhiều ảnh/trang, reader có `getNumImages(...)`, `getImageMetadata(i)`, `getWidth(i)`, `getHeight(i)`, `read(i)`. Mục `ImageIO.read` thông thường chỉ trả một `BufferedImage`, vì vậy không thể từ nó mà suy ra số trang/tất cả metadata.

Nếu `writer.canWriteSequence()` báo có hỗ trợ, quy trình ghi nhiều ảnh thường như sau:

```java
// Mảnh minh họa: writer đã setOutput(...), pages và writeParam hợp lệ.
writer.prepareWriteSequence(null);
for (IIOImage page : pages) {
    writer.writeToSequence(page, writeParam);
}
writer.endWriteSequence();
```

`pages` ở đây là collection `IIOImage` đã chuẩn bị sẵn, không phải biến tự có của Java. Trong ứng dụng thực, kiểm soát exception và trạng thái sequence, không gọi `endWriteSequence` nếu sequence chưa được khởi tạo thành công, đóng image stream, và **đọc lại số trang lẫn metadata** sau khi ghi. `canWriteSequence()==true` không đồng nghĩa hỗ trợ mọi kiểu pixel/kiểu nén.

TIFF có extension như Exif, GeoTIFF và BigTIFF. JDK có các tag set công khai cho Exif/GPS/GeoTIFF, nhưng điều đó **không bảo đảm mọi kiểu TIFF extension, sub-IFD hoặc BigTIFF đều được plugin tích hợp xử lý đầy đủ**. Với tag chưa biết, `TIFFImageReadParam` có các lựa chọn `addAllowedTagSet(...)` và `setReadUnknownTags(true)` khi provider hỗ trợ. Dùng dựa trên yêu cầu/định dạng thực, không tự bật chế độ đọc tất cả tag không tin cậy.

## 9. An toàn và lỗi thường gặp

Một TIFF nhỏ có thể khai báo raster rất lớn hoặc chứa nhiều trang/field khiến hệ thống tiêu thụ quá nhiều bộ nhớ/thời gian khi xử lý. Với file không tin cậy, giới hạn dung lượng, số trang, kích thước pixel (nhân width × height bằng `long`), loại compression, thời gian xử lý và lượng metadata chấp nhận. Dùng phân quyền thư mục tạm và kiểm tra kết quả đọc; metadata EXIF/GPS có thể gây lộ thông tin không mong muốn.

Luôn đóng `ImageInputStream`/`ImageOutputStream` bằng try-with-resources; gọi `reader.dispose()` và `writer.dispose()` khi xong. `ImageIO` có thể sử dụng disk cache tùy cấu hình; kiểm tra môi trường container/permission thay vì giả định luôn chạy chỉ trong RAM.

| Lỗi/triệu chứng | Nguyên nhân có thể | Giải pháp |
| --- | --- | --- |
| Không có reader/writer TIFF | Thiếu module/provider hoặc cấu hình runtime khác | Kiểm tra `getImageReadersByFormatName`/`getImageWritersByFormatName` trên đúng runtime |
| Có reader nhưng file không mở được | File hỏng, nén/extension không hỗ trợ | Dùng `getImageReaders(input)` và kiểm tra thông báo `IIOException` |
| Metadata trả `null` | Reader không cung cấp hoặc được yêu cầu bỏ qua | Kiểm tra `setInput(input, seekForwardOnly, ignoreMetadata)` |
| `TIFFDirectory.createFromMetadata` lỗi | Format metadata không tương thích, tree sai | Kiểm tra `getMetadataFormatNames()` và TIFF native metadata |
| `getTIFFField` trả `null` | Tag không có hoặc nằm trong IFD khác | Tìm đúng IFD, kiểm tra tag set |
| Ghi xong mất description/Exif | Writer bỏ field hoặc chuyển đổi metadata làm mất thông tin | Lấy default metadata từ writer, đọc lại output |
| DPI sai | Bỏ qua unit hoặc type rational | Đọc `XResolution`, `YResolution` và `ResolutionUnit` |
| Ảnh bị xoay ngược | Orientation và pixel bị xử lý không nhất quán | Xác minh raster với metadata orientation |
| Chỉ đọc trang đầu | Dùng `ImageIO.read` một ảnh | Dùng `ImageReader` theo chỉ số và giới hạn trang |
| Nén không ghi được | Kiểu nén không hợp kiểu raster/provider | Kiểm tra write param, test encode/decode |
| Chậm hoặc hết bộ nhớ | Số trang, pixel, strip/tile quá lớn | Giới hạn input, xử lý từng phần, giám sát tài nguyên |

## 10. Checklist áp dụng

- [ ] Xác minh reader/writer TIFF trên runtime triển khai thực, không chỉ trên IDE.
- [ ] Phân biệt đăng ký theo tên định dạng và khả năng đọc một file thật.
- [ ] Kiểm tra pixel type, compression và multi-page theo yêu cầu ứng dụng.
- [ ] Đọc metadata từng trang; xác nhận native TIFF metadata và xử lý tag thiếu.
- [ ] Ghi metadata qua `TIFFDirectory.getAsMetadata`; kiểm tra type/count đúng.
- [ ] Đọc lại output để xác nhận pixel, kích thước, số trang và các tag quan trọng.
- [ ] Kiểm soát EXIF/GPS, orientation, resolution và metadata riêng cần bảo toàn.
- [ ] Áp giới hạn input, quản lý streams và gọi `dispose()`.

## Tài liệu chính thức

- [Java SE 26 — javax.imageio.plugins.tiff](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/javax/imageio/plugins/tiff/package-summary.html)
- [Java SE 26 — TIFFDirectory](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/javax/imageio/plugins/tiff/TIFFDirectory.html)
- [Java SE 26 — TIFFField](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/javax/imageio/plugins/tiff/TIFFField.html)
- [Java SE 26 — TIFFImageReadParam](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/javax/imageio/plugins/tiff/TIFFImageReadParam.html)
- [Java SE 26 — ImageIO](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/javax/imageio/ImageIO.html)
- [Java SE 26 — TIFF Metadata Format Specification and Usage Notes](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/javax/imageio/metadata/doc-files/tiff_metadata.html)

Với hệ thống thực, luôn đối chiếu tài liệu đúng phiên bản JDK/provider đang chạy và kiểm thử bằng các file TIFF thực tế; không suy diễn từ đặc tính của một runtime khác.
