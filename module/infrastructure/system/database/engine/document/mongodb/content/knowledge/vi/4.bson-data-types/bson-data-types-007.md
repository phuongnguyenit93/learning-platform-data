# BSON Binary, UUID và quy ước biểu diễn UUID giữa các driver MongoDB

MongoDB lưu document bằng **BSON (Binary JSON)**. Ngoài các kiểu như string, number, date và ObjectId, BSON có kiểu **Binary** dành cho chuỗi byte. **UUID (Universally Unique Identifier)** là một ứng dụng đặc biệt của kiểu Binary: một định danh 128 bit thường được viết dưới dạng chuỗi có dấu gạch nối nhưng có thể lưu gọn trong BSON dưới dạng 16 byte.

Điểm dễ gây lỗi khi làm việc với UUID là **hai giá trị trông giống nhau ở dạng chuỗi chưa chắc được lưu giống nhau trong MongoDB**. Các driver cũ từng dùng những cách sắp xếp byte khác nhau và BSON binary subtype khác nhau. Vì thế, khi Java, Python, C# hoặc Node.js cùng truy cập một collection, ứng dụng cần thống nhất quy ước lưu và đọc UUID.

Bài học giải thích cấu trúc Binary, UUID chuẩn, legacy UUID, cách các driver biểu diễn UUID, hậu quả khi cấu hình không nhất quán và hướng xử lý dữ liệu cũ.

## 1. Phân biệt Binary, UUID và chuỗi UUID

Ba cách biểu diễn sau có thể cùng mô tả một định danh ở tầng nghiệp vụ, nhưng là những **giá trị BSON khác kiểu hoặc khác subtype**:

| Biểu diễn | Nội dung | Cách MongoDB nhìn nhận |
| --- | --- | --- |
| String | "00112233-4455-6677-8899-aabbccddeeff" | BSON string |
| Binary subtype 4 | 16 byte theo thứ tự UUID chuẩn | BSON Binary, UUID standard |
| Binary subtype 3 | 16 byte theo quy ước UUID legacy | BSON Binary, UUID legacy |

Ví dụ một document lưu UUID dưới dạng chuỗi:

~~~javascript
{
  sessionId: "00112233-4455-6677-8899-aabbccddeeff",
  userId: "user-101",
  status: "ACTIVE"
}
~~~

Document khác lưu UUID kiểu BSON Binary chuẩn:

~~~javascript
{
  sessionId: UUID("00112233-4455-6677-8899-aabbccddeeff"),
  userId: "user-101",
  status: "ACTIVE"
}
~~~

Trong **mongosh**, hàm **UUID(...)** tạo giá trị UUID dưới dạng BSON Binary **subtype 4**. Hai document trên không có cùng BSON type cho field **sessionId**. Vì vậy, truy vấn bằng string không tự động tương đương với truy vấn bằng UUID nhị phân:

~~~javascript
// Tìm giá trị BSON string.
db.sessions.find({
  sessionId: "00112233-4455-6677-8899-aabbccddeeff"
});

// Tìm giá trị BSON Binary UUID standard.
db.sessions.find({
  sessionId: UUID("00112233-4455-6677-8899-aabbccddeeff")
});
~~~

MongoDB không tự động chuyển string UUID thành BSON Binary UUID trong thao tác so khớp bình thường.

### Tại sao lưu UUID bằng Binary?

UUID có 128 bit, tương đương **16 byte dữ liệu định danh**. Dạng văn bản quen thuộc có 32 ký tự hex và 4 dấu gạch nối, tổng cộng 36 ký tự. Binary giúp lưu trực tiếp 16 byte định danh, trong khi string lưu các ký tự văn bản và có thêm overhead của BSON string.

Tuy vậy, Binary không tự động giải quyết các vấn đề về lựa chọn khóa, tính ngẫu nhiên, khả năng sắp xếp hay phân phối dữ liệu. Kích thước index và đặc tính insert còn phụ thuộc schema, phiên bản UUID, giá trị khóa và workload.

## 2. BSON Binary có cấu trúc gì?

BSON định nghĩa kiểu phần tử **Binary Data**, thường ký hiệu bằng type code **0x05**. Giá trị Binary mang hai thông tin chính:

1. **Payload**: dãy byte thực tế cần lưu.
2. **Subtype**: một mã cho biết dãy byte đó được diễn giải theo quy ước nào.

Có thể hình dung một field Binary như sau:

~~~text
Document BSON
└── field: "payload"
    ├── BSON type: Binary (0x05)
    └── Binary value
        ├── byte length
        ├── subtype
        └── raw bytes
~~~

Kích thước và subtype nằm trong định dạng BSON. Thực tế, BSON Binary còn có quy tắc mã hóa độ dài cụ thể; trong bài này, điều quan trọng là **subtype là một phần của giá trị Binary**, không phải một field nghiệp vụ độc lập bên cạnh payload.

### Một số Binary subtype thường gặp

| Subtype | Tên thường dùng | Mục đích |
| --- | --- | --- |
| **0x00** | Generic Binary | Dữ liệu nhị phân thông thường |
| **0x02** | Old Binary | Cách biểu diễn binary cũ, không nên chọn cho dữ liệu mới |
| **0x03** | UUID (Legacy) | UUID theo các quy ước driver cũ |
| **0x04** | UUID (Standard) | UUID 16 byte theo thứ tự byte chuẩn |
| **0x05** | MD5 | Dữ liệu theo subtype MD5 chuyên biệt |
| **0x06** | Encrypted BSON value | Dữ liệu dùng trong cơ chế mã hóa BSON được hỗ trợ |
| **0x80–0xFF** | User-defined | Phạm vi subtype do ứng dụng tự định nghĩa |

Bảng chỉ tập trung vào những subtype hữu ích để phân biệt Binary và UUID; MongoDB còn quy định các subtype khác cho những tính năng cụ thể.

**Subtype không phải là cơ chế bảo mật.** Dữ liệu mang subtype 0x06 không có nghĩa mọi giá trị Binary đều được mã hóa. Chọn subtype phải theo đúng định dạng và tính năng mà ứng dụng sử dụng.

### Khi nào dùng Binary nói chung?

Binary phù hợp với payload có kích thước hợp lý, chẳng hạn mã băm, chữ ký, dữ liệu giao thức hoặc một đoạn byte mà ứng dụng cần giữ nguyên. Ví dụ minh họa:

~~~javascript
{
  fileName: "avatar.png",
  checksum: BinData(0, "AQIDBA==")
}
~~~

Đoạn **AQIDBA==** là biểu diễn Base64 của bốn byte **01 02 03 04**; **BinData(0, ...)** trong mongosh biểu diễn generic Binary subtype 0.

Đây chỉ là ví dụ byte nhỏ. BSON document thông thường có giới hạn kích thước **16 MiB**. Khi lưu file lớn, cần cân nhắc **GridFS** hoặc hệ thống lưu trữ file phù hợp; không nên đưa file bất kỳ vào một document Binary không giới hạn.

## 3. UUID là gì?

**UUID** là định danh 128 bit, thường dùng để nhận diện một phiên làm việc, đối tượng nghiệp vụ, sự kiện hoặc tài nguyên qua nhiều hệ thống.

Ví dụ:

~~~text
00112233-4455-6677-8899-aabbccddeeff
~~~

Dạng văn bản chuẩn có năm nhóm hex, theo mẫu:

~~~text
8 ký tự - 4 ký tự - 4 ký tự - 4 ký tự - 12 ký tự
xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
~~~

Một UUID có **version** và **variant** theo chuẩn áp dụng. Có nhiều phiên bản UUID, chẳng hạn UUID v4 dựa trên số ngẫu nhiên và UUID v7 có thành phần thời gian. MongoDB Binary subtype 4 chỉ xác định cách **biểu diễn byte** của UUID trong BSON; subtype 4 không tự chỉ ra UUID thuộc version nào.

### UUID không phải ObjectId

MongoDB thường tự tạo **ObjectId** làm field **_id** nếu client không cung cấp định danh. ObjectId và UUID là hai kiểu khác nhau:

| Đặc điểm | ObjectId | UUID |
| --- | --- | --- |
| Kích thước payload | 12 byte | 16 byte |
| Biểu diễn mongosh | ObjectId("...") | UUID("...") |
| BSON type | ObjectId | Binary subtype 4 nếu dùng chuẩn |
| Dùng làm _id | Có | Có |
| Tự động tạo khi thiếu _id | Thường dùng ObjectId | Phải được ứng dụng/driver chọn hoặc tạo rõ ràng |

Bạn có thể dùng UUID cho **_id**:

~~~javascript
db.sessions.insertOne({
  _id: UUID("00112233-4455-6677-8899-aabbccddeeff"),
  userId: "user-101",
  createdAt: new Date()
});
~~~

MongoDB không bắt buộc field **_id** phải là ObjectId. Tuy nhiên, nếu dùng UUID làm **_id**, cần thống nhất BSON representation ngay từ đầu vì định danh không được cập nhật bằng thao tác update thông thường.

### UUID không phải token đăng nhập

UUID giúp định danh, nhưng không mặc nhiên là bằng chứng xác thực hay quyền truy cập. Dù UUID được sinh ngẫu nhiên, ứng dụng vẫn cần xác thực người dùng và phân quyền khi truy cập dữ liệu theo UUID. Không nên coi việc “khó đoán ID” là lớp bảo vệ duy nhất.

## 4. UUID standard: Binary subtype 4 và thứ tự byte

Trong cách biểu diễn hiện đại, UUID được lưu bằng **BSON Binary subtype 4 (0x04)** với đúng **16 byte theo thứ tự chuẩn của UUID**.

Lấy UUID minh họa:

~~~text
00112233-4455-6677-8899-aabbccddeeff
~~~

Bỏ dấu gạch nối, đọc hai ký tự hex thành một byte:

~~~text
00 11 22 33 44 55 66 77 88 99 aa bb cc dd ee ff
~~~

Đây là thứ tự byte chuẩn khi ghi UUID subtype 4. Dấu gạch nối chỉ là cách hiển thị ở dạng text; chúng không nằm trong 16 byte Binary.

~~~text
Chuỗi UUID:
  00112233-4455-6677-8899-aabbccddeeff
      |
      | chuyển các cặp hex thành byte
      v
Payload BSON UUID standard:
  00 11 22 33 44 55 66 77 88 99 aa bb cc dd ee ff

Subtype:
  0x04
~~~

Trong mongosh:

~~~javascript
const id = UUID("00112233-4455-6677-8899-aabbccddeeff");

db.sessions.insertOne({
  sessionId: id,
  status: "ACTIVE"
});

db.sessions.findOne({ sessionId: id });
~~~

**Cùng một UUID chuẩn** sẽ có cùng 16 byte payload và subtype 4 giữa các driver tuân theo standard UUID representation, bất kể tên class UUID trong ngôn ngữ lập trình khác nhau.

## 5. Tại sao có UUID Legacy subtype 3?

Các driver MongoDB đời cũ không thống nhất cách mã hóa UUID thành BSON Binary. Một số driver dùng **subtype 3 (0x03)** và lựa chọn thứ tự byte theo cách biểu diễn UUID/GUID của ngôn ngữ đó.

Vấn đề nằm ở hai lớp:

- **Subtype**: legacy subtype 3 khác standard subtype 4.
- **Thứ tự byte**: giữa các legacy driver, 16 byte có thể được sắp xếp khác nhau.

Vì vậy, chỉ nhìn một giá trị Binary subtype 3 **không đủ** để xác định chính xác chuỗi UUID ban đầu. Cần biết driver nào đã tạo ra dữ liệu và cấu hình UUID representation lúc ghi.

### Bốn quy ước quan trọng

Tên thường gặp trong driver và tài liệu MongoDB:

| Quy ước | BSON subtype | Thứ tự 16 byte | Ý nghĩa |
| --- | --- | --- | --- |
| **STANDARD** | 4 | Thứ tự UUID chuẩn | Khuyến nghị cho dữ liệu mới |
| **PYTHON_LEGACY** | 3 | Thứ tự UUID chuẩn | Payload giống STANDARD nhưng subtype khác |
| **JAVA_LEGACY** | 3 | Đảo chiều byte trong từng nhóm 8 byte | Quy ước từ Java driver cũ |
| **CSHARP_LEGACY** | 3 | Little-endian ở ba thành phần đầu của GUID | Quy ước từ .NET/C# driver cũ |

Cùng chuỗi UUID minh họa:

~~~text
00112233-4455-6677-8899-aabbccddeeff
~~~

Sự khác biệt có thể trình bày cụ thể:

| Representation | Subtype | Payload hex (16 byte) |
| --- | --- | --- |
| STANDARD | 04 | 00 11 22 33 44 55 66 77 88 99 aa bb cc dd ee ff |
| PYTHON_LEGACY | 03 | 00 11 22 33 44 55 66 77 88 99 aa bb cc dd ee ff |
| JAVA_LEGACY | 03 | 77 66 55 44 33 22 11 00 ff ee dd cc bb aa 99 88 |
| CSHARP_LEGACY | 03 | 33 22 11 00 55 44 77 66 88 99 aa bb cc dd ee ff |

Những byte trong bảng được tính từ chuỗi UUID minh họa. Tên **JAVA_LEGACY**, **CSHARP_LEGACY** và **PYTHON_LEGACY** là tên **quy ước mã hóa UUID**, không phải khẳng định mọi phiên bản Java/C#/Python driver hiện tại đều mặc định ghi kiểu cũ.

### 5.1. PYTHON_LEGACY

PYTHON_LEGACY lưu 16 byte theo thứ tự chuẩn nhưng sử dụng subtype 3:

~~~text
Chuỗi:  00112233-4455-6677-8899-aabbccddeeff
Bytes:  00 11 22 33 44 55 66 77 88 99 aa bb cc dd ee ff
Subtype: 03
~~~

Điểm nguy hiểm: payload giống STANDARD nhưng MongoDB vẫn coi là Binary khác vì **subtype 03 ≠ subtype 04**.

### 5.2. JAVA_LEGACY

JAVA_LEGACY đảo thứ tự byte trong **mỗi nửa 8 byte**:

~~~text
STANDARD:
  00 11 22 33 44 55 66 77 | 88 99 aa bb cc dd ee ff

JAVA_LEGACY:
  77 66 55 44 33 22 11 00 | ff ee dd cc bb aa 99 88
~~~

Không phải Java UUID tự mang thứ tự sai. Đây là **cách một quy ước BSON UUID legacy tuần tự hóa UUID vào Binary**, nên muốn đọc đúng dữ liệu cũ phải chọn đúng representation.

### 5.3. CSHARP_LEGACY

Quy ước CSHARP_LEGACY xuất phát từ cách biểu diễn byte truyền thống của **System.Guid**:

~~~text
UUID:
  00112233-4455-6677-8899-aabbccddeeff

STANDARD:
  00 11 22 33 | 44 55 | 66 77 | 88 99 aa bb cc dd ee ff

CSHARP_LEGACY:
  33 22 11 00 | 55 44 | 77 66 | 88 99 aa bb cc dd ee ff
~~~

Nhóm 4 byte đầu, nhóm 2 byte tiếp theo và nhóm 2 byte thứ ba bị đổi endianness; 8 byte cuối giữ nguyên. Điều này giải thích vì sao một GUID lưu bằng driver .NET cũ có thể hiển thị thành UUID khác nếu phần mềm khác giải mã nhầm theo thứ tự chuẩn.

## 6. Hai loại lỗi tương thích điển hình

### 6.1. Cùng UUID nghiệp vụ, khác BSON Binary

Giả sử ứng dụng A lưu UUID chuẩn:

~~~text
Representation: STANDARD
Subtype:        04
Payload:        00 11 22 33 44 55 66 77 88 99 aa bb cc dd ee ff
~~~

Ứng dụng B lưu cùng UUID theo PYTHON_LEGACY:

~~~text
Representation: PYTHON_LEGACY
Subtype:        03
Payload:        00 11 22 33 44 55 66 77 88 99 aa bb cc dd ee ff
~~~

Dù payload giống nhau, giá trị BSON **khác subtype**. Một điều kiện equality bằng UUID subtype 4 sẽ không tự khớp document lưu subtype 3.

Nếu field **sessionId** có unique index, không nên kỳ vọng index hợp nhất mọi dạng biểu diễn UUID thành một định danh nghiệp vụ. Giá trị Binary lưu khác subtype hoặc khác byte có thể không được nhìn nhận là bản sao trùng về mặt BSON.

### 6.2. Cùng 16 byte, giải mã ra UUID khác

Giả sử đọc payload JAVA_LEGACY bằng decoder STANDARD mà không nhận biết quy ước cũ.

~~~text
Payload lấy từ database:
  77 66 55 44 33 22 11 00 ff ee dd cc bb aa 99 88
~~~

Đối với dữ liệu nguồn JAVA_LEGACY, payload này đại diện UUID ban đầu:

~~~text
00112233-4455-6677-8899-aabbccddeeff
~~~

Nếu công cụ diễn giải nguyên payload như thứ tự chuẩn, giá trị text có thể trở thành:

~~~text
77665544-3322-1100-ffee-ddccbbaa9988
~~~

Các thư viện hiện đại có thể **từ chối** giải mã subtype không phù hợp thay vì âm thầm trả UUID sai. Cách xử lý cụ thể phụ thuộc driver và cấu hình. Vấn đề chính vẫn là: **không thể đoán representation từ hình thức UUID ở tầng ứng dụng**.

## 7. Đọc Binary trong mongosh và Extended JSON

Trong mongosh, giá trị UUID standard có thể được tạo bằng:

~~~javascript
UUID("00112233-4455-6677-8899-aabbccddeeff")
~~~

Dữ liệu BSON Binary khi chuyển thành **Extended JSON** dạng canonical thường có cấu trúc:

~~~json
{
  "sessionId": {
    "$binary": {
      "base64": "ABEiM0RVZneImaq7zN3u/w==",
      "subType": "04"
    }
  }
}
~~~

Trong biểu diễn này:

- **base64** mô tả payload byte ở dạng văn bản để có thể truyền trong JSON.
- **subType** là mã subtype ở dạng chuỗi hex; **04** tương ứng UUID standard.
- Tài liệu JSON chỉ là cách **biểu diễn** Binary ra text; BSON lưu payload byte trực tiếp, không lưu nguyên Base64 làm string nghiệp vụ.

Nếu đổi **subType** thành **03** mà không thay byte, ta có Binary với payload như cũ nhưng subtype legacy. Việc đổi subtype theo cách này **không phải cách chuyển đổi UUID legacy tổng quát**, vì JAVA_LEGACY và CSHARP_LEGACY còn cần chuyển thứ tự byte.

Trong mongosh có thể quan sát Extended JSON canonical của một document:

~~~javascript
const document = db.sessions.findOne({ status: "ACTIVE" });

print(
  EJSON.stringify(document, null, 2, { relaxed: false })
);
~~~

Phản hồi thực tế phụ thuộc document và kiểu dữ liệu đã lưu. Khi kiểm tra dữ liệu nhập từ hệ thống cũ, nên ghi nhận **cả subtype lẫn byte**, rồi đối chiếu với representation đã được driver nguồn sử dụng.

### Xem field có kiểu Binary hay không

~~~javascript
db.sessions.find({
  sessionId: { $type: "binData" }
});
~~~

Điều kiện **$type: "binData"** lọc theo kiểu BSON Binary nói chung. Nó không đủ để kết luận giá trị là UUID standard subtype 4; Binary generic, legacy UUID và những subtype khác cũng thuộc kiểu này.

## 8. Quy ước UUID trong các driver hiện đại

Mỗi ngôn ngữ có kiểu UUID riêng:

| Hệ sinh thái | Kiểu UUID ở ứng dụng | Lưu MongoDB theo standard |
| --- | --- | --- |
| Java | java.util.UUID | BSON Binary subtype 4 khi codec được cấu hình STANDARD |
| Python | uuid.UUID | BSON Binary subtype 4 khi uuidRepresentation là STANDARD |
| .NET/C# | System.Guid | BSON Binary subtype 4 khi serializer dùng GuidRepresentation.Standard |
| Node.js | BSON UUID từ driver | BSON Binary subtype 4 |
| mongosh | UUID("...") | BSON Binary subtype 4 |

Quy tắc cho hệ thống mới: **dùng STANDARD/subtype 4 nhất quán ở cả bên ghi, bên đọc và khi tạo điều kiện truy vấn**.

Đừng lấy tên ngôn ngữ làm bằng chứng cho representation đang được dùng. Driver hiện đại có thể có mặc định khác driver cũ; thậm chí giữa các phiên bản cùng ngôn ngữ, hành vi tự động chuyển UUID có thể thay đổi. Khi tương tác với dữ liệu hiện hữu, hãy kiểm tra **phiên bản driver, cấu hình serializer/codec và dữ liệu thực tế**.

### 8.1. Java Sync Driver: cấu hình STANDARD

Đoạn Java sau minh họa cách cấu hình **MongoClientSettings** để chuyển **java.util.UUID** thành BSON Binary subtype 4.

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;

import org.bson.Document;
import org.bson.UuidRepresentation;

import java.util.UUID;

public class StandardUuidExample {

    public static void main(String[] args) {
        String uri = "mongodb://localhost:27017";

        MongoClientSettings settings = MongoClientSettings.builder()
                .applyConnectionString(new ConnectionString(uri))
                .uuidRepresentation(UuidRepresentation.STANDARD)
                .build();

        UUID sessionId =
                UUID.fromString("00112233-4455-6677-8899-aabbccddeeff");

        try (MongoClient client = MongoClients.create(settings)) {
            MongoDatabase database = client.getDatabase("demo");
            MongoCollection<Document> sessions =
                    database.getCollection("sessions");

            sessions.insertOne(
                    new Document("sessionId", sessionId)
                            .append("status", "ACTIVE")
            );

            Document result = sessions.find(
                    Filters.eq("sessionId", sessionId)
            ).first();

            System.out.println(result);
        }
    }
}
~~~

Điểm cần nhận diện:

- **UUID.fromString(...)** tạo UUID trong bộ nhớ Java.
- **UuidRepresentation.STANDARD** quy định cách mã hóa/giải mã UUID giữa Java và BSON.
- Điều kiện **Filters.eq(...)** dùng cùng UUID representation khi driver tuần tự hóa giá trị truy vấn.
- Nếu database trước đó lưu field bằng **JAVA_LEGACY subtype 3**, truy vấn STANDARD sẽ không tự động tìm thấy các bản ghi cũ.

Các phiên bản Java Driver mới sử dụng chế độ như **UNSPECIFIED** để tránh tự diễn giải UUID mơ hồ. Nếu ứng dụng gặp lỗi mã hóa **java.util.UUID** khi representation chưa chỉ định, cần cấu hình rõ thay vì đoán subtype dựa trên byte.

**Lưu ý vận hành:** Ví dụ giả định có MongoDB sẵn tại localhost, người dùng có quyền ghi và đã thêm dependency MongoDB Java Sync Driver. Ví dụ insert có thể tạo document mới mỗi lần chạy vì **sessionId** chưa được đặt làm unique key.

### 8.2. Python/PyMongo: cấu hình CodecOptions

Trong Python, **uuid.UUID** là kiểu đối tượng ở ứng dụng. Với PyMongo hiện đại, nên khai báo rõ representation trên collection cần làm việc.

~~~python
from uuid import UUID

from bson.binary import UuidRepresentation
from bson.codec_options import CodecOptions
from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017")
database = client.get_database("demo")

sessions = database.get_collection(
    "sessions",
    codec_options=CodecOptions(
        uuid_representation=UuidRepresentation.STANDARD
    )
)

session_id = UUID("00112233-4455-6677-8899-aabbccddeeff")

sessions.insert_one({
    "sessionId": session_id,
    "status": "ACTIVE"
})

document = sessions.find_one({"sessionId": session_id})
print(document)
~~~

**CodecOptions** cho PyMongo biết cách mã hóa và giải mã UUID. Với dữ liệu cũ, nếu collection được lưu bằng PYTHON_LEGACY, JAVA_LEGACY hoặc CSHARP_LEGACY, cần chọn đúng quy ước khi đọc/di chuyển dữ liệu.

PyMongo còn hỗ trợ thao tác trực tiếp với **bson.binary.Binary** để chủ động tạo hoặc giải mã UUID theo một representation:

~~~python
from uuid import UUID

from bson.binary import Binary, UuidRepresentation

original = UUID("00112233-4455-6677-8899-aabbccddeeff")

legacy_binary = Binary.from_uuid(
    original,
    uuid_representation=UuidRepresentation.JAVA_LEGACY
)

print(legacy_binary.subtype)  # 3
print(
    legacy_binary.as_uuid(
        uuid_representation=UuidRepresentation.JAVA_LEGACY
    )
)
~~~

Ví dụ này chỉ tạo và đọc giá trị Binary trong bộ nhớ. Nó minh họa nguyên tắc **biết representation khi decode**. Không nên thấy subtype 3 rồi tự mặc định mọi dữ liệu là JAVA_LEGACY.

### 8.3. Node.js: BSON UUID

MongoDB Node.js Driver cung cấp kiểu **UUID**, có thể dùng trực tiếp khi insert và query.

~~~javascript
import { MongoClient, UUID } from "mongodb";

const client = new MongoClient("mongodb://localhost:27017");

async function main() {
  const sessionId = new UUID(
    "00112233-4455-6677-8899-aabbccddeeff"
  );

  await client.connect();

  try {
    const collection = client
      .db("demo")
      .collection("sessions");

    await collection.insertOne({
      sessionId,
      status: "ACTIVE"
    });

    const document = await collection.findOne({
      sessionId
    });

    console.log(document);
  } finally {
    await client.close();
  }
}

main().catch(console.error);
~~~

Kiểu BSON UUID của Node.js tương ứng UUID standard. Khi hệ thống đồng thời có Java hoặc Python, các driver cần thống nhất **subtype 4**, không chỉ thống nhất chuỗi UUID hiển thị trong log.

Nếu ứng dụng Node.js tự truyền một **Buffer** 16 byte, đừng giả định driver sẽ tự nhận biết đó là UUID. Cần dùng đúng class hoặc cấu hình BSON Binary/subtype. Buffer và UUID là hai ý định dữ liệu khác nhau.

### 8.4. C#/.NET: chú ý GuidRepresentation

.NET sử dụng **System.Guid**. Trong các phiên bản driver cũ, cách biểu diễn GUID đã từng khác chuẩn UUID theo thứ tự byte và subtype. Do đó, hệ thống .NET kết nối với dữ liệu legacy cần chú ý:

- Dữ liệu được ghi bằng **CSHARP_LEGACY** hay **STANDARD**?
- Cấu hình **GuidSerializer** / **GuidRepresentation** của phiên bản driver đang chạy là gì?
- Entity/POCO field, điều kiện filter và công cụ migration có đang dùng cùng một representation không?

Với hệ thống mới, thiết kế nên chọn **GuidRepresentation.Standard** cho dữ liệu BSON UUID; với hệ thống hiện hữu, phải đối chiếu thực tế trước khi đổi cấu hình.

API serializer và vị trí cấu hình có thể thay đổi giữa các phiên bản MongoDB .NET Driver. Không nên sao chép tùy chọn cấu hình của driver đời cũ vào driver mới mà không kiểm tra phiên bản.

## 9. Cấu hình đọc và ghi phải đồng nhất

Một hệ thống nhiều dịch vụ có thể gặp tình huống:

~~~text
Service Java
  java.util.UUID ── STANDARD ──> subtype 04

Service Python
  uuid.UUID ── PYTHON_LEGACY ──> subtype 03

Service .NET
  System.Guid ── CSHARP_LEGACY ──> subtype 03, byte order khác

MongoDB collection: sessions
  sessionId có nhiều BSON representations
~~~

Kết quả có thể là:

1. Service A lưu document thành công nhưng Service B tìm bằng UUID string tương đương lại không thấy.
2. Một số document được decode thành UUID sai nếu dùng nhầm quy ước byte.
3. Truy vấn filter hoặc unique index hoạt động khác kỳ vọng do subtype/payload khác.
4. Khi xuất JSON, UUID bị chuyển thành string hoặc Extended JSON Binary tùy công cụ.
5. Một migration có thể “thành công” ở tầng thao tác ghi nhưng làm sai định danh nếu chỉ đổi subtype mà không đổi byte.

### Quy ước nên được ghi rõ trong hợp đồng dữ liệu

Ví dụ mô tả schema nội bộ:

~~~yaml
collection: sessions
fields:
  sessionId:
    meaning: "Định danh phiên"
    logicalType: UUID
    bsonType: binData
    binarySubtype: "04"
    uuidRepresentation: STANDARD
    required: true
    indexed: true
~~~

YAML trên là **minh họa tài liệu thiết kế**, không phải một lệnh MongoDB tạo collection hoặc schema validation tự động. Nó diễn đạt những thông tin mà các service cần thống nhất.

Nếu hệ thống dùng string UUID làm định dạng được chuẩn hóa ở tầng database, hãy ghi rõ **BSON string** trong hợp đồng. Điều cần tránh là để mỗi service tự chọn một biểu diễn.

### Cẩn trọng với JSON API và message queue

Một API có thể truyền UUID như string:

~~~json
{
  "sessionId": "00112233-4455-6677-8899-aabbccddeeff"
}
~~~

Đây là cách trao đổi thuận tiện giữa dịch vụ, nhưng khi ghi vào MongoDB, adapter phải **chuyển string thành UUID/Binary standard** nếu schema BSON yêu cầu subtype 4.

Tương tự, nhận một document từ MongoDB rồi chuyển qua JSON không có nghĩa field giữ nguyên BSON type. Nếu parse lại JSON và insert vào collection khác, field có thể biến thành string khi thiếu bước chuyển đổi đúng.

## 10. Xử lý dữ liệu UUID legacy một cách có kiểm soát

Giả sử hệ thống có nhiều document lưu UUID subtype 3 và muốn chuyển sang subtype 4. Việc chuyển đổi đúng đòi hỏi biết **dữ liệu gốc đến từ representation nào**.

### Bước 1: Khảo sát thực tế

Xác định:

- Collection và field nào có UUID.
- UUID đang là **string**, **Binary subtype 3**, **Binary subtype 4**, hay pha trộn.
- Driver nào từng ghi dữ liệu; phiên bản và cấu hình UUID representation lúc đó.
- Field UUID có dùng làm **_id**, shard key, khóa logic, giá trị unique index hoặc tham chiếu ở collection khác không.
- Có service nào đang ghi định dạng legacy trong lúc chuyển đổi không.

Có thể đọc document mẫu và quan sát Extended JSON canonical:

~~~javascript
const sample = db.sessions.findOne();

print(
  EJSON.stringify(sample, null, 2, { relaxed: false })
);
~~~

Để diễn giải Binary subtype 3, **không nên dựa riêng vào phần Base64**; cần biết byte order của dữ liệu nguồn.

### Bước 2: Xác nhận quy ước bằng dữ liệu đã biết

Chọn một số document mà bạn biết UUID gốc từ log hoặc hệ thống phát sinh. So sánh:

~~~text
UUID gốc được xác nhận:
  00112233-4455-6677-8899-aabbccddeeff

Binary trong MongoDB:
  subtype = 03
  payload = 77 66 55 44 33 22 11 00 ff ee dd cc bb aa 99 88

Diễn giải theo JAVA_LEGACY:
  00112233-4455-6677-8899-aabbccddeeff
~~~

Từ đó có cơ sở xác định dữ liệu đang tuân theo JAVA_LEGACY. Nếu trong cùng collection có dữ liệu từ nhiều driver đời cũ, chỉ một representation cho toàn bộ collection có thể không đủ; cần xác định theo nguồn hoặc nhóm dữ liệu.

### Bước 3: Chuyển về UUID logic rồi mã hóa lại

Quy trình chuyển đổi đúng có ba bước rõ ràng:

~~~text
BSON Binary legacy subtype 3
        |
        | Giải mã với representation gốc
        v
UUID logic (128 bit)
        |
        | Mã hóa với STANDARD
        v
BSON Binary standard subtype 4
~~~

Ví dụ Python minh họa phép chuyển đổi **trong bộ nhớ**, với dữ liệu nguồn đã được xác nhận là JAVA_LEGACY:

~~~python
from bson.binary import Binary, UuidRepresentation

def java_legacy_to_standard(value: Binary) -> Binary:
    uuid_value = value.as_uuid(
        uuid_representation=UuidRepresentation.JAVA_LEGACY
    )
    return Binary.from_uuid(
        uuid_value,
        uuid_representation=UuidRepresentation.STANDARD
    )
~~~

Ví dụ trên không tự chạy trên toàn collection và cũng không xử lý string hoặc UUID thuộc representation khác. Chỉ áp dụng khi đã biết nguồn dữ liệu thực sự là JAVA_LEGACY.

**Không chuyển subtype 03 thành 04 bằng cách đổi một byte metadata cho mọi document.** Với JAVA_LEGACY và CSHARP_LEGACY, còn phải đưa 16 byte về đúng thứ tự chuẩn.

### Bước 4: Lập kế hoạch cập nhật dữ liệu

Khi cần di chuyển dữ liệu thật:

1. Sao lưu và thử chuyển đổi trên môi trường có thể phục hồi; xác nhận UUID trước/sau giữ nguyên ý nghĩa.
2. Chuẩn hóa điểm ghi mới về STANDARD để không phát sinh thêm giá trị legacy.
3. Chuyển đổi theo nhóm có thể kiểm soát và lưu kết quả đối chiếu giữa UUID nguồn, payload cũ và payload mới.
4. Cập nhật cùng lúc các tham chiếu, filter, index hoặc hệ thống downstream có sử dụng định danh.
5. Chỉ loại bỏ logic đọc legacy sau khi không còn dữ liệu và client phụ thuộc vào nó.

Nếu UUID là **_id**, không thể đơn giản chạy **$set: { _id: ... }** vì field _id bất biến trong update thông thường. Trường hợp này thường cần tạo document mới với _id chuẩn, điều chỉnh tham chiếu liên quan và kế hoạch cutover phù hợp.

Nếu UUID là **shard key**, việc đổi cách biểu diễn còn tác động tới cơ chế phân vùng, đường đi truy vấn và quy tắc cập nhật shard key; không nên thực hiện bằng script chuyển byte đơn giản.

### Bước 5: Xác nhận sự tương thích giữa service

Sau khi chuyển đổi, cần bảo đảm mọi service:

- Ghi UUID mới bằng subtype 4 và thứ tự byte standard.
- Đọc giá trị BSON đã lưu theo cùng quy ước.
- Tạo filter tìm kiếm với cùng BSON representation.
- Không biến UUID thành string khi đi qua adapter JSON trừ khi schema lưu trữ quy định rõ string.
- Giữ nguyên ý nghĩa UUID khi qua Java, Python, Node.js và .NET.

Một test tích hợp nhiều driver có thể dùng **cùng UUID biết trước**: service này ghi, service kia đọc và truy vấn theo UUID đó, sau đó đảo vai trò. Việc đối chiếu cần xem **subtype và payload**, ngoài chuỗi UUID hiển thị.

## 11. UUID, index và điều kiện truy vấn

Giả sử collection lưu:

~~~javascript
db.sessions.insertOne({
  sessionId: UUID("00112233-4455-6677-8899-aabbccddeeff"),
  status: "ACTIVE"
});
~~~

Tạo index:

~~~javascript
db.sessions.createIndex(
  { sessionId: 1 },
  { unique: true }
);
~~~

Khi field luôn là UUID standard, ứng dụng có thể truy vấn theo giá trị đồng nhất:

~~~javascript
db.sessions.findOne({
  sessionId: UUID("00112233-4455-6677-8899-aabbccddeeff")
});
~~~

Nếu hệ thống đã tồn tại document với UUID tương đương nhưng lưu dạng string hoặc subtype 3, truy vấn trên có thể không tìm thấy chúng. Unique index cũng không thể tự hiểu rằng một string, một UUID subtype 3 và một UUID subtype 4 mang cùng định danh nghiệp vụ.

### Không lẫn kiểu BSON và logic ứng dụng

Ví dụ sau là ba giá trị khác nhau ở tầng BSON:

~~~text
"00112233-4455-6677-8899-aabbccddeeff"     (string)

Binary subtype 03 + 16 byte legacy          (binData)

Binary subtype 04 + 16 byte standard        (binData)
~~~

Ứng dụng có thể coi chúng là cùng UUID sau khi decode và chuẩn hóa, nhưng MongoDB không tự áp dụng phép chuẩn hóa nghiệp vụ đó cho mọi phép equality.

### Lựa chọn UUID làm _id

Khi dùng UUID làm primary identifier, cần cân nhắc thêm:

- Khả năng sinh ID trước khi insert ở phía client.
- Phân phối giá trị khóa khi nhiều writer tạo dữ liệu đồng thời.
- Tác động của kiểu UUID (ví dụ ngẫu nhiên hoặc có tính thời gian) đối với tính cục bộ của index.
- Quy ước subtype/byte trong mọi client; đây là điều kiện cần cho truy vấn tìm document bằng _id.
- Khả năng tương thích với API, log, event và hệ thống khác.

UUID subtype 4 xác định cách lưu byte; nó **không tự bảo đảm** đặc tính sắp xếp, hiệu năng hay độ an toàn của chiến lược sinh ID.

## 12. Các nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| UUID là một BSON type độc lập giống string | BSON UUID thông thường là **Binary subtype 4** |
| Binary chỉ dùng để lưu file | Binary còn lưu UUID, payload giao thức, byte tùy ý và các subtype chuyên biệt |
| Hai chuỗi UUID giống nhau thì MongoDB luôn so khớp được | So khớp còn phụ thuộc BSON type, subtype và payload byte |
| Legacy UUID luôn có cùng thứ tự byte | JAVA_LEGACY, CSHARP_LEGACY và PYTHON_LEGACY có những quy ước khác nhau |
| Subtype 3 cho biết dữ liệu chắc chắn được ghi từ Java | Subtype 3 không cho biết driver nguồn hoặc endianness |
| STANDARD và PYTHON_LEGACY giống hoàn toàn | Payload có thể giống nhưng subtype lần lượt là 4 và 3 |
| Có thể chuyển tất cả subtype 3 sang 4 bằng cách sửa subtype | Cần decode đúng representation rồi encode lại theo STANDARD |
| Base64 trong Extended JSON nghĩa là MongoDB lưu string Base64 | Base64 chỉ dùng để biểu diễn byte trong JSON; BSON Binary lưu payload byte |
| UUID và ObjectId có cùng cấu trúc | ObjectId là BSON type riêng với payload 12 byte; UUID standard là Binary subtype 4, 16 byte |
| Driver hiện tại mặc định giống driver cũ | Mặc định và API cấu hình phụ thuộc driver/phiên bản, cần kiểm tra rõ |
| $type: "binData" chỉ bắt UUID standard | Điều kiện này bao gồm các Binary subtype khác |
| UUID khó đoán nên đủ để phân quyền | UUID là định danh, không thay thế kiểm tra quyền truy cập |

## 13. Thực hành: quan sát UUID standard và legacy

Các ví dụ dưới đây dùng một UUID minh họa nhất quán:

~~~text
00112233-4455-6677-8899-aabbccddeeff
~~~

### Bài tập A: lưu UUID chuẩn bằng mongosh

~~~javascript
use uuid_demo

const sessionId = UUID("00112233-4455-6677-8899-aabbccddeeff");

db.sessions.insertOne({
  _id: sessionId,
  userId: "user-101",
  createdAt: new Date()
});

db.sessions.findOne({ _id: sessionId });
~~~

Hãy xác định:

1. Field **_id** thuộc BSON type nào?
2. UUID standard sử dụng subtype nào?
3. Payload định danh có bao nhiêu byte?
4. Nếu truy vấn bằng string UUID, MongoDB có tự chuyển string sang Binary subtype 4 không?

### Bài tập B: xem Extended JSON

~~~javascript
const document = db.sessions.findOne({
  _id: UUID("00112233-4455-6677-8899-aabbccddeeff")
});

print(EJSON.stringify(document, null, 2, { relaxed: false }));
~~~

Quan sát cấu trúc **$binary**, **base64** và **subType**. Hãy giải thích vì sao **base64** trong JSON không làm đổi BSON type đã được lưu.

### Bài tập C: so sánh các representation trong Python

~~~python
from uuid import UUID
from bson.binary import Binary, UuidRepresentation

value = UUID("00112233-4455-6677-8899-aabbccddeeff")

for name, representation in [
    ("STANDARD", UuidRepresentation.STANDARD),
    ("PYTHON_LEGACY", UuidRepresentation.PYTHON_LEGACY),
    ("JAVA_LEGACY", UuidRepresentation.JAVA_LEGACY),
    ("CSHARP_LEGACY", UuidRepresentation.CSHARP_LEGACY),
]:
    binary = Binary.from_uuid(
        value,
        uuid_representation=representation
    )

    print(name, "subtype=", binary.subtype)
    print("bytes=", bytes(binary).hex())
    print(
        "decoded=",
        binary.as_uuid(uuid_representation=representation)
    )
~~~

Bài tập giúp quan sát rằng **STANDARD** và **PYTHON_LEGACY** cùng thứ tự byte nhưng khác subtype; **JAVA_LEGACY** và **CSHARP_LEGACY** còn khác thứ tự byte.

### Bài tập D: đặt câu hỏi cho một hệ thống nhiều driver

Một hệ thống có ba service:

~~~text
Java service:     ghi UUID vào MongoDB
Python service:   đọc và truy vấn UUID từ MongoDB
Node.js service:  nhận UUID dạng JSON string từ HTTP API
~~~

Hãy xác định quy ước cần thống nhất tại ba ranh giới:

1. Java chuyển **java.util.UUID** thành BSON Binary theo representation nào?
2. Python cần codec nào để đọc và dùng UUID làm điều kiện tìm kiếm?
3. Node.js nhận string HTTP thì cần chuyển sang kiểu nào trước khi ghi/truy vấn BSON?
4. Khi migration dữ liệu subtype 3, vì sao phải biết driver nguồn?
5. Nếu UUID nằm ở **_id**, vì sao không thể đổi subtype bằng update thông thường?

Nếu trả lời được, bạn đã nắm được điểm cốt lõi: **UUID là một định danh logic; MongoDB lưu nó dưới một BSON Binary representation cụ thể. Sự tương thích giữa các driver phụ thuộc vào cả subtype và thứ tự 16 byte, không chỉ chuỗi UUID mà lập trình viên nhìn thấy.**

## Tài liệu tham khảo

- [MongoDB Manual — BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/)
- [MongoDB Manual — Extended JSON](https://www.mongodb.com/docs/manual/reference/mongodb-extended-json/)
- [MongoDB Java Sync Driver — Documentation](https://www.mongodb.com/docs/drivers/java/sync/current/)
- [PyMongo — Documentation](https://pymongo.readthedocs.io/en/stable/)
