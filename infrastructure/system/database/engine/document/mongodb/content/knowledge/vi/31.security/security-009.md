# Client Side Field Level Encryption và Queryable Encryption trong MongoDB

## 1. Vì sao mã hóa ổ đĩa và TLS vẫn chưa đủ?

Một ứng dụng quản lý hồ sơ khách hàng lưu các document:

```javascript
{
  _id: ObjectId("66a000000000000000000335"),
  tenantId: "ORG-A",
  fullName: "Khách hàng A",
  email: "person@example.test",
  nationalId: "ID-00991",
  incomeVnd: NumberLong("24000000"),
  internalNote: "Ghi chú nhạy cảm"
}
```

Ứng dụng phải cho nhân viên được cấp quyền **tìm đúng khách hàng theo mã định danh**, đôi khi lọc theo mức thu nhập, nhưng người quản trị hạ tầng database hoặc người đánh cắp backup **không nên đọc được các trường nhạy cảm ở dạng rõ**.

Hai lớp bảo vệ thường gặp:

- **TLS/in transit:** mã hóa đường truyền giữa ứng dụng và MongoDB.
- **Encryption at rest:** bảo vệ dữ liệu trên ổ đĩa/snapshot trong phạm vi cơ chế được triển khai.

Hai lớp này rất quan trọng nhưng dữ liệu có thể vẫn được **giải mã phía server MongoDB** để thực hiện truy vấn. Người có quyền đọc collection qua database có thể nhìn thấy giá trị rõ nếu chỉ dựa vào các lớp trên.

**Client-Side Field Level Encryption (CSFLE)** và **Queryable Encryption (QE)** thuộc nhóm **in-use encryption**: trường được mã hóa **ở phía client/driver trước khi gửi** vào MongoDB. Máy chủ lưu ciphertext, còn client có quyền và có khóa hợp lệ giải mã khi đọc.

Bài học thuộc chương **Bảo mật** của module **Database Engine Document MongoDB**, tập trung vào cách hai công nghệ bảo vệ dữ liệu, khả năng truy vấn, cấu hình khóa, giới hạn và cách triển khai an toàn.

Sau bài học, bạn có thể:

1. Phân biệt TLS, encryption at rest, CSFLE và Queryable Encryption.
2. Giải thích **deterministic** và **randomized** CSFLE, rủi ro phân tích tần suất.
3. Giải thích vì sao QE vẫn truy vấn được ciphertext được mã hóa ngẫu nhiên, nhưng có thêm metadata/chi phí.
4. Phân biệt **CMK**, **DEK**, **Key Vault** và KMS; hiểu mất khóa có thể đồng nghĩa mất dữ liệu.
5. Chọn đúng kiểu truy vấn **equality, range, prefix, suffix, substring** theo MongoDB version và kiểu BSON.
6. Thiết kế encrypted schema/`encryptedFields`; không tạo index thường trên dữ liệu QE rồi nhầm là index hỗ trợ truy vấn mã hóa.
7. Hiểu các giới hạn về unique, TTL, sharding, migration, update, aggregation và collation.
8. Tạo thử nghiệm CSFLE explicit và QE automatic trong Node.js **trên cluster lab**, dùng khóa giả lập chỉ dành cho học tập.
9. Lập kế hoạch phân quyền, rotation/backup, giám sát, incident response và kiểm tra dữ liệu không lộ plaintext.

## 2. Kiến trúc mã hóa tại client

### 2.1. Luồng ghi

```text
         Application / MongoDB Driver
                    |
          plaintext trong bộ nhớ
                    |
              chọn field
                    |
       DEK + encryption library
                    |
           ciphertext (BinData)
                    |
               TLS network
                    |
                    v
               MongoDB Server
                    |
             lưu ciphertext
                    |
             Disk / Replicas
```

MongoDB server có thể biết collection, tên field, một số metadata và các trường không mã hóa. Nó **không tự có CMK/DEK rõ** để giải mã trường được bảo vệ đúng cách.

### 2.2. Luồng đọc

```text
            MongoDB Server
                   |
          trả ciphertext
                   |
                   v
             MongoDB Driver
                   |
        lấy DEK đã được bảo vệ
        và mở qua KMS phù hợp
                   |
                decrypt
                   |
                   v
        plaintext ở ứng dụng
```

Chỉ client đã được cấu hình và cấp quyền đến **đúng key vault/KMS** mới giải mã được. Nhưng khi đã giải mã vào bộ nhớ ứng dụng, dữ liệu vẫn có thể bị lộ qua logs, crash dumps, response API hoặc thao tác của một service bị xâm nhập.

### 2.3. Ranh giới bảo vệ và threat model

Hai công nghệ chủ yếu bảo vệ khi attacker:

- Chỉ có bản sao database/backup.
- Có quyền đọc ciphertext trong database nhưng không có quyền truy cập khóa.
- Có thể nhìn traffic mạng mà không nắm khóa client.
- Có quyền DBA rộng trên server nhưng không có khóa decryption của ứng dụng.

Chúng **không tự bảo vệ** khỏi:

- Client có quyền giải mã bị chiếm quyền điều khiển.
- Mã độc chạy trong cùng process với driver, lấy plaintext/CMK.
- API vô tình trả trường nhạy cảm cho người dùng sai quyền.
- KMS credentials hoặc CMK bị lộ.
- Side-channel/phân tích query logs và snapshot trong một số threat model.
- Dữ liệu không mã hóa, field names, kích thước document hoặc pattern access còn lộ.

Đặc biệt, **QE không bảo đảm an toàn trước kẻ tấn công có quyền truy cập bền bỉ vào môi trường hoặc có cả snapshot và query transcripts/logs**; phải đối chiếu threat model chính thức, nhất là range queries. Không hứa “zero-knowledge tuyệt đối trong mọi hoàn cảnh”.

## 3. So sánh CSFLE và Queryable Encryption

### 3.1. CSFLE: hai cách mã hóa

CSFLE hỗ trợ:

- **Deterministic:** với cùng DEK, kiểu BSON và plaintext, mã hóa cho kết quả giống nhau. Điều này cho phép một số **equality queries** trên trường đã mã hóa.
- **Randomized:** cùng plaintext được mã hóa thành ciphertext khác nhau giữa các lượt. Giảm rủi ro quan sát trùng/tần suất, nhưng **không hỗ trợ truy vấn trực tiếp theo giá trị field đó** bằng equality.

### 3.2. Queryable Encryption: mã hóa ngẫu nhiên mà vẫn truy vấn

QE dùng một cấu trúc mã hóa **randomized** và các dữ liệu phụ trợ được bảo vệ để hỗ trợ tìm kiếm trên field mã hóa mà không cần MongoDB giải mã plaintext của field.

Các kiểu truy vấn được hỗ trợ theo phiên bản gồm:

- **Equality**: kiểm tra bằng/khác, thuộc tập theo operator được hỗ trợ.
- **Range**: điều kiện lớn hơn/nhỏ hơn cho những BSON types phù hợp.
- **Prefix/suffix/substring** trên chuỗi ở các phiên bản có tính năng tương ứng.
- **None**: mã hóa trường nhưng **không** cho truy vấn theo giá trị trường đó.

QE không biến mọi MongoDB operator thành phép toán được hỗ trợ trên ciphertext. Nó vẫn có giới hạn rõ về BSON types, command, update và aggregation.

### 3.3. Bảng quyết định

| Tiêu chí | CSFLE deterministic | CSFLE randomized | Queryable Encryption |
| --- | --- | --- | --- |
| Mã hóa ở client | Có | Có | Có |
| Cùng plaintext → cùng ciphertext | Có | Không | Không theo cơ chế randomized |
| Equality query | Có với cấu hình/driver phù hợp | Không | Có nếu field được cấu hình `equality` hoặc kiểu phù hợp |
| Range query | Không phải khả năng CSFLE thông thường | Không | Có từ phiên bản hỗ trợ |
| Prefix/suffix/substring | Không | Không | Có ở MongoDB 9.0 GA với driver/thư viện tương thích |
| Frequency leakage từ ciphertext bằng nhau | Có rủi ro, nhất là low-cardinality | Giảm đáng kể | Không lộ tính bằng nhau qua ciphertext đơn giản; còn threat model khác |
| Cấu trúc quản lý | Encryption schema/DEKs | Encryption schema/DEKs | `encryptedFields`, key vault, ESC/ECOC, `__safeContent__` |
| Metadata/search overhead | Tùy số field | Tùy số field | Tăng writes/storage và chi phí query |
| Use case | ID/email cần exact match, cardinality cao | Ghi chú hoặc payload chỉ đọc theo ID document | Trường nhạy cảm phải tìm theo equality/range/partial string |

**Khuyến nghị lựa chọn:** bắt đầu từ **yêu cầu truy vấn**. Field chỉ hiển thị sau khi lấy document theo `_id` thường không cần queryable index. Nếu vẫn cần query trên dữ liệu mã hóa, đánh giá QE thay vì tự giảm bảo mật bằng cách dùng deterministic cho một field cardinality thấp.

## 4. Phiên bản và khả năng hỗ trợ

Đây là chủ đề **phụ thuộc phiên bản mạnh**:

| Khả năng | Mốc quan trọng |
| --- | --- |
| CSFLE | Có từ MongoDB Server 4.2 trong các điều kiện hỗ trợ |
| QE equality | Được triển khai và GA trong dòng MongoDB 7.0, với khả năng/preview ở release trước |
| QE range | MongoDB Server 8.0 trở lên |
| QE prefix/suffix/substring trên chuỗi | **MongoDB Server 9.0 trở lên** cho bản GA, cần driver/thư viện tương thích |
| Prefix/suffix/substring public preview | Có ở dòng 8.2/8.3; **không tương thích trực tiếp với GA 9.0** theo ghi chú migration |
| Automatic encryption | Phụ thuộc phiên bản driver, **MongoDB Atlas/Enterprise** và Automatic Encryption Shared Library |
| Explicit encryption/decryption | Có đường triển khai trong môi trường khác khi driver và server hỗ trợ; xem hạn chế cụ thể |

Tháng 9/2026, MongoDB công bố **GA** cho prefix, suffix và substring QE. Đặc biệt, nếu đang dùng bản **public preview** trên 8.2/8.3, **không nâng cấp theo giả định ciphertext/index có thể dùng thẳng với 9.0**; xem tài liệu migration chính thức.

Không kết luận hỗ trợ chỉ từ `mongosh --version`. Hãy kiểm tra **server, FCV, driver, cryptographic shared library, topology, edition/plan và KMS configuration**.

### 4.1. MongoDB Community và Automatic Encryption

Tài liệu Quick Start của MongoDB phân biệt: **automatic encryption** dành cho môi trường Atlas/Enterprise tương thích; MongoDB Community không hỗ trợ cùng đường **automatic** trong ví dụ chính thức, nhưng một số khả năng **explicit encryption** có thể dùng tùy server/driver. Không tự lấy mã automatic QE áp lên standalone Community rồi kết luận “QE không hoạt động”.

### 4.2. Replica set và sharded cluster

QE hỗ trợ **replica set và sharded cluster** trong các phiên bản tương thích; tài liệu hiện hành ghi **không hỗ trợ standalone** hoặc **secondary reads** trong ngữ cảnh QE. Với sharding, còn những giới hạn riêng cho shard key, indexes và cấu trúc encrypted metadata.

Đừng dùng cùng một đoạn demo trên standalone `mongod` để xác nhận mọi cơ chế QE.

## 5. Envelope encryption: CMK, DEK và Key Vault

### 5.1. Ba lớp trách nhiệm

```text
Customer-managed KMS
      |
      | giữ Customer Master Key (CMK)
      |
      +--- unwrap / wrap ---> Data Encryption Key (DEK)
                                     |
                                     | mã hóa field ở client
                                     v
                           MongoDB encrypted fields
                                     |
                                     v
                          Ciphertext in documents

MongoDB Key Vault collection
      |
      +-- lưu DEK đã được CMK wrap
      +-- key metadata / keyAltNames
```

- **CMK (Customer Master Key)**: khóa gốc do tổ chức kiểm soát, nên nằm trong dịch vụ quản lý khóa từ xa.
- **DEK (Data Encryption Key)**: khóa dùng để mã hóa/giải mã dữ liệu ở mức field.
- **Key Vault collection**: MongoDB collection lưu **DEK đã được mã hóa/wrapped**, cùng metadata; không phải nơi lưu CMK rõ.
- **KMS**: AWS KMS, Azure Key Vault, Google Cloud KMS, KMIP hoặc provider tương thích theo tài liệu.

Client có khóa/thẩm quyền KMS phù hợp để unwrap DEK rồi xử lý mã hóa. MongoDB Server không tự sở hữu plaintext DEK.

### 5.2. Key Vault là dữ liệu quan trọng cần backup

Ví dụ:

```javascript
{
  _id: UUID("00000000-0000-4000-8000-000000000335"),
  keyMaterial: BinData(0, "...wrapped DEK..."),
  masterKey: { provider: "aws", /* ... */ },
  keyAltNames: ["tenant-a-private-fields"],
  status: 0,
  creationDate: ISODate("2026-11-14T04:00:00Z")
}
```

Đây chỉ là hình dạng minh họa. **Không ghi keyMaterial plaintext vào log**, không copy Key Vault ra kho công cộng và không dùng UUID ví dụ làm khóa thật.

Với `keyAltNames`, Key Vault cần **unique index** phù hợp để alias không trỏ tới hai DEK khác nhau. Giới hạn quyền ghi/xóa key riêng biệt với quyền CRUD của business collection.

### 5.3. Mất khóa có thể là mất dữ liệu không phục hồi

Nếu mất CMK cần để mở DEK, hoặc xóa DEK cần để decrypt ciphertext, dữ liệu có thể **không thể đọc lại** dù còn nguyên backup database.

Do đó backup/recovery phải bao gồm:

1. Dữ liệu và metadata MongoDB.
2. Key Vault.
3. Khả năng khôi phục quyền truy cập KMS/CMK cùng lịch sử khóa.
4. Cấu hình encrypted fields và driver hỗ trợ.
5. Test khôi phục trên môi trường tách biệt, có access controls.

**Không** thực hiện `deleteKey()` hoặc hủy CMK để “dọn khóa cũ” khi chưa chắc chắn không còn bất cứ ciphertext nào phụ thuộc chúng.

### 5.4. Local KMS chỉ dành cho thử nghiệm

MongoDB hỗ trợ **local key provider** dùng khóa 96 byte, tiện cho lab:

```javascript
import { randomBytes } from "node:crypto";

const localMasterKey = randomBytes(96);
const kmsProviders = {
  local: {
    key: localMasterKey
  }
};
```

Đây là **khóa vừa tạo trong bộ nhớ** để học, không phải mô hình production. Nếu process thoát và bạn mất `localMasterKey`, những DEK đã wrap bằng nó sẽ không còn giải mã được. Không hardcode khóa này trong source/git, không log hoặc lưu vào tài liệu chia sẻ.

Trong production phải dùng **remote KMS**, RBAC, audit, separation of duties và quy trình rotation/restore.

## 6. CSFLE deterministic: truy vấn được nhưng có thể lộ tần suất

### 6.1. Hai ciphertext giống nhau là một dấu hiệu

Giả sử một field `countryCode` chỉ có hai giá trị:

```text
VN, VN, VN, VN, VN, US, VN, VN, US, VN
```

Mã hóa deterministic khiến:

```text
VN -> CIPH_A
US -> CIPH_B

CIPH_A, CIPH_A, CIPH_A, CIPH_A, ...
```

Dù attacker không có DEK, họ có thể biết trường này có **hai nhóm giá trị**, nhóm lớn chiếm đa số. Nếu biết phân phối ngoài đời, họ có thể suy luận ngược — **frequency analysis**.

Cần cân nhắc đặc biệt với:

- status có 2–5 giá trị;
- quốc gia, giới tính, nhóm thu nhập ít bucket;
- boolean, mã trạng thái xác thực;
- bất kỳ field có cardinality thấp hoặc phân phối rất lệch.

Không chọn deterministic chỉ vì viết `find({field:value})` dễ hơn.

### 6.2. Kỹ thuật deterministic không tạo unique business invariant

Nếu cần email duy nhất, không được tự nghĩ “ciphertext deterministic giống nhau nên sẽ luôn chống trùng”. Uniqueness còn phụ thuộc unique index, collation, normalization, sharding và mọi client đều mã hóa bằng cùng quy tắc/DEK/BSON type.

Nếu nhiều client dùng khóa khác hoặc ghi plaintext trực tiếp, cùng email có thể xuất hiện ở nhiều biểu diễn. Nên thiết kế business uniqueness riêng theo invariant, nhất là khi QE dùng randomized ciphertext.

### 6.3. Các field không nên deterministic

Trường dữ liệu không được query theo giá trị:

```javascript
{
  internalNote: "Ghi chú riêng",
  medicalHistory: { /* thông tin cấu trúc nhạy cảm */ },
  attachments: [ /* ... */ ]
}
```

thường là ứng viên cho **randomized CSFLE** hoặc QE `queryType:none`, tùy loại BSON và nhu cầu lưu trữ.

CSFLE **không hỗ trợ deterministic encryption cho toàn bộ array/object**, trong khi randomized có thể mã hóa toàn bộ array/object theo quy tắc schema. Một khi đã mã hóa cả object thành ciphertext, MongoDB không thể query bình thường vào field con bên trong.

## 7. CSFLE automatic và explicit

### 7.1. Automatic

Với automatic CSFLE:

```text
Application:
    collection.insertOne({ passport: "A12345" })
                     |
                     v
    Driver + schemaMap + KMS
                     |
                 encrypt
                     |
                     v
MongoDB:
    { passport: BinData(encrypted subtype, ...) }
```

Ứng dụng sử dụng API CRUD tương đối tự nhiên; driver đọc encryption rules và mã hóa các field phù hợp.

Một **`schemaMap` do client kiểm soát** có thể tránh tình huống server bị chiếm quyền sửa remote schema để dẫn client đến cấu hình kém an toàn. Nhưng phải quản lý schema của tất cả ứng dụng cùng ghi collection.

### 7.2. Explicit

Với explicit CSFLE, application gọi mã hóa:

```javascript
const ciphertext = await clientEncryption.encrypt(
  "ID-00991",
  {
    keyId: dataKeyId,
    algorithm:
      "AEAD_AES_256_CBC_HMAC_SHA_512-Deterministic"
  }
);

await db.collection("people").insertOne({
  tenantId: "ORG-A",
  nationalId: ciphertext
});
```

Khi đọc:

```javascript
const raw = await db.collection("people").findOne({
  tenantId: "ORG-A"
});

const nationalId = await clientEncryption.decrypt(
  raw.nationalId
);
```

Ưu điểm là ứng dụng kiểm soát rõ trường nào được mã hóa. Nhược điểm là dễ **quên encrypt tại một write path** hoặc **quên decrypt tại một read path**. Cần test, code review và server-side schema enforcement khi có thể.

### 7.3. Tránh double encryption

Không tự explicit-encrypt một field rồi gửi qua automatic-encryption client đang có rule encrypt chính field đó mà chưa kiểm tra contract driver. Có thể xảy ra lỗi hoặc double-processing không mong muốn.

Cần chọn rõ:

- **Automatic client:** application gửi plaintext trong memory, driver mã hóa.
- **Explicit encryption:** application tạo BSON encrypted value rồi dùng đường đọc/ghi phù hợp.

Khi một hệ thống có nhiều service, tất cả writer phải tuân theo cùng quy tắc field, key và loại encryption.

## 8. Thực hành CSFLE explicit bằng Node.js

### 8.1. Yêu cầu môi trường

Bài lab này dùng **MongoDB deployment thử nghiệm** có hỗ trợ CSFLE, Node.js driver tương thích và thư viện mã hóa. Chỉ dùng dữ liệu giả. Không chạy trên collection khách hàng, tài chính hay hồ sơ thật.

Cần cài packages phù hợp với driver version:

```bash
npm install mongodb mongodb-client-encryption
```

Cách cài/thư viện native có thể khác theo OS, bản Node.js và driver; hãy xem tài liệu compatibility của version đang dùng.

Sử dụng một MongoDB URI test trong `MONGODB_URI`. Không đặt connection string chứa mật khẩu vào source hoặc commit Git.

### 8.2. Một ví dụ explicit encryption trọn vẹn

Code CommonJS:

```javascript
const {
  MongoClient,
  ClientEncryption,
  ObjectId
} = require("mongodb");

const { randomBytes } = require("node:crypto");

async function main() {
  const uri = process.env.MONGODB_URI;
  if (!uri) {
    throw new Error("MONGODB_URI is required");
  }

  const client = new MongoClient(uri);
  await client.connect();

  try {
    const db = client.db("mongo_encryption_row335_lab");
    const runId = new ObjectId().toHexString();

    // Tạo namespace riêng, tránh đụng dữ liệu người khác.
    const collectionName = "csfle_" + runId;
    const vaultName = "vault_" + runId;
    const collection = db.collection(collectionName);
    const vault = db.collection(vaultName);

    await vault.createIndex(
      { keyAltNames: 1 },
      { unique: true }
    );

    // Chỉ dành cho lab: mất khóa này sẽ mất khả năng decrypt.
    const localMasterKey = randomBytes(96);

    const encryption = new ClientEncryption(client, {
      keyVaultNamespace: db.databaseName + "." + vaultName,
      kmsProviders: {
        local: { key: localMasterKey }
      }
    });

    const dataKeyId = await encryption.createDataKey(
      "local",
      { keyAltNames: ["row335-key-" + runId] }
    );

    const encryptCode = (value) =>
      encryption.encrypt(value, {
        keyId: dataKeyId,
        algorithm:
          "AEAD_AES_256_CBC_HMAC_SHA_512-Deterministic"
      });

    const encryptNote = (value) =>
      encryption.encrypt(value, {
        keyId: dataKeyId,
        algorithm:
          "AEAD_AES_256_CBC_HMAC_SHA_512-Random"
      });

    const value = "LAB-PRIVATE-ID-335";
    const encryptedCodeA = await encryptCode(value);
    const encryptedCodeB = await encryptCode(value);
    const encryptedNoteA = await encryptNote("Ghi chú demo");
    const encryptedNoteB = await encryptNote("Ghi chú demo");

    const fileId = new ObjectId();

    await collection.insertOne({
      _id: fileId,
      runId,
      publicLabel: "Lab customer",
      privateCode: encryptedCodeA,
      privateNote: encryptedNoteA
    });

    // Truy vấn equality: phải mã hóa query value giống quy tắc.
    const hit = await collection.findOne({
      _id: fileId,
      privateCode: encryptedCodeB
    });

    if (!hit) {
      throw new Error("Cannot find encrypted document");
    }

    const decryptedCode = await encryption.decrypt(
      hit.privateCode
    );
    const decryptedNote = await encryption.decrypt(
      hit.privateNote
    );

    console.log({
      collectionName,
      runId,
      foundByDeterministicEquality: Boolean(hit),
      codeRoundTripCorrect: decryptedCode === value,
      noteRoundTripCorrect:
        decryptedNote === "Ghi chú demo",
      ciphertextIsBinary:
        hit.privateCode?._bsontype === "Binary"
    });

    // Không in plaintext thật, ciphertext hay key material.
    // Không thể query equality trên privateNote random.

    // Dọn chỉ record thuộc lượt thử.
    const removed = await collection.deleteOne({
      _id: fileId,
      runId
    });
    console.log({ deleted: removed.deletedCount });

    // Collection/vault lab vẫn còn. Chỉ thu hồi qua runbook
    // quản trị lab sau khi chắc chắn không cần DEK/khóa.
  } finally {
    await client.close();
  }
}

main().catch((error) => {
  console.error(error.name, error.message);
  process.exitCode = 1;
});
```

Trong lab, cả `encryptedCodeA` và `encryptedCodeB` mã hóa cùng chuỗi bằng cùng DEK, algorithm và kiểu BSON, nên phù hợp cho equality. `encryptedNoteA`/`encryptedNoteB` có ciphertext khác nhau trong trường hợp bình thường, nhưng cả hai vẫn decrypt được bằng DEK.

**Đây không phải kiểm định mật mã.** Không dùng việc so các buffer trong một test nhỏ làm bằng chứng về độ an toàn thuật toán; tính chất được xác định bởi đặc tả/driver. Đồng thời không copy localMasterKey vào logs. Nếu cần đọc lại record ở process khác, phải quản lý khóa an toàn; mã lab này cố ý dùng khóa ephemeral.

### 8.3. Điều gì xảy ra khi client không có khóa?

Client MongoDB bình thường nhìn vào field encrypted thường nhận một **BSON Binary ciphertext**, không phải chuỗi rõ. Nếu nó gửi filter `privateCode:"LAB-PRIVATE-ID-335"` trực tiếp mà không mã hóa, query sẽ không match giá trị deterministic ciphertext.

Cần hiểu ba trường hợp khác nhau:

1. Không có encryption config: chỉ có BSON ciphertext.
2. Có explicit encryption helper: ứng dụng tự encrypt query và decrypt kết quả.
3. Có automatic encryption config: driver xử lý theo schema/operation được hỗ trợ.

Không kỳ vọng MongoDB Server giải mã thay client.

## 9. Queryable Encryption hoạt động ra sao?

### 9.1. Khác biệt quan trọng so với deterministic

CSFLE deterministic hỗ trợ equality bằng cách ciphertext của cùng plaintext giống nhau. QE muốn **cùng plaintext tạo ciphertext khác nhau**, đồng thời tìm kiếm được nhờ **structured encrypted index** và query processing phù hợp.

```text
Application searches nationalId = "ID-00991"
                    |
                    v
Driver + DEK + query analysis
                    |
       biến query sang token/biểu diễn
        được giao thức QE hỗ trợ
                    |
                    v
MongoDB Server
   |
   +--- encrypted collection documents
   +--- encrypted state metadata (ESC)
   +--- encrypted compaction metadata (ECOC)
   +--- __safeContent__ in documents
                    |
             chọn candidates
                    |
                    v
       trả encrypted documents
                    |
                    v
        Driver decrypt for app
```

Không được tự suy ra server nhìn thấy plaintext chỉ vì server thực hiện phép tìm kiếm. Ngược lại, cũng không được hứa cấu trúc truy vấn không rò rỉ **bất kỳ** thông tin nào trong mọi threat model.

### 9.2. Các collection metadata và field hệ thống

Với collection `patients`, QE có thể tạo:

```text
patients
enxcol_.patients.esc
enxcol_.patients.ecoc
```

Các khái niệm:

- **ESC (Encrypted State Collection)**: metadata phục vụ chỉ mục/query trên dữ liệu được mã hóa.
- **ECOC (Encrypted Compaction Collection)**: metadata hỗ trợ quản lý/compaction.
- **`__safeContent__`**: field do QE quản lý bên trong document mã hóa, phục vụ query indexing.

**Không trực tiếp sửa, xóa, rename, backfill hoặc tự tạo `__safeContent__`/ESC/ECOC.** Tài liệu MongoDB cảnh báo việc đó có thể làm sai kết quả truy vấn và ảnh hưởng bảo mật.

### 9.3. Chi phí so với plain collection

Với một field có equality query, một insert có thể kéo theo các writes vào collection chính **và hai metadata collections**. Nếu nhiều field được index, overhead tăng tương ứng.

Tài liệu MongoDB nêu một encrypted collection có thể cần dung lượng **gấp khoảng 2–3 lần** so với collection chưa mã hóa trong một số tình huống; đó không phải hệ số cố định cho mọi workload.

Các query range/partial string thường có cấu hình và chi phí khác equality. Do đó phải benchmark với **dữ liệu và phân phối giá trị thực**, không chỉ đo trên 10 document demo.

## 10. Định nghĩa encrypted schema của QE

### 10.1. `encryptedFields` và `fields`

Ví dụ:

```javascript
const encryptedFields = {
  fields: [
    {
      path: "nationalId",
      bsonType: "string",
      queries: {
        queryType: "equality"
      }
    },
    {
      path: "incomeVnd",
      bsonType: "long",
      queries: {
        queryType: "range",
        min: Long.fromNumber(0),
        max: Long.fromNumber(1000000000)
      }
    },
    {
      path: "internalNote",
      bsonType: "string"
      // Không có queries => encrypted, not queryable.
    }
  ]
};
```

Đây là **mẫu thiết kế**; muốn thực thi phải có driver/BSON Long, key vault/KMS, quyền, và tạo collection qua workflow QE. `keyId` có thể được chỉ định với DEK UUID hợp lệ; helper `createEncryptedCollection()` có thể tạo DEK cho field thiếu `keyId`.

### 10.2. Cấp quyền query theo từng field

Với field:

```javascript
{
  path: "nationalId",
  bsonType: "string",
  queries: { queryType: "equality" }
}
```

Ứng dụng được cấu hình đúng có thể gửi query tương tự:

```javascript
await encryptedCollection.findOne({
  nationalId: "ID-00991"
});
```

Driver nhận ra phép so sánh trên field encrypted và biến đổi theo giao thức QE.

Nếu field chỉ có:

```javascript
{
  path: "internalNote",
  bsonType: "string"
}
```

driver có thể mã hóa/giải mã nó nhưng **không thể làm equality query theo plaintext** của field đó qua QE.

### 10.3. Một field không bật mọi query type tùy ý

Theo tài liệu MongoDB 9.0:

- Field queryable dùng một trong các cấu hình equality/range phù hợp, không đồng thời “bật tất cả” tùy ý.
- Prefix và suffix có thể cùng bật cho một field khi cấu hình thỏa các ràng buộc.
- Substring **không được kết hợp** với prefix/suffix trên cùng field.
- Những kiểu query chỉ hỗ trợ BSON types tương ứng.
- Query type là thuộc tính được quyết định khi tạo encrypted collection; **không tự sửa type cho existing field** rồi mong index cũ tự chuyển đổi.

Muốn đổi khả năng query, cần lên kế hoạch tạo encrypted collection mới và migration theo quy trình chính thức.

### 10.4. Không mã hóa `_id` bằng QE

QE không cho cấu hình `_id` làm encrypted field. Thiết kế định danh document ổn định, không đưa plaintext nhạy cảm vào `_id` nếu không có lý do.

Nếu khóa nghiệp vụ (ví dụ national ID) cần bí mật, dùng `_id` kỹ thuật, encrypted field riêng và một kiến trúc uniqueness tương thích thay vì dùng national ID làm `_id` plaintext.

## 11. QE equality: trường nào phù hợp?

### 11.1. Ví dụ tra theo mã định danh

Trường `nationalId` là chuỗi:

```javascript
{
  path: "nationalId",
  bsonType: "string",
  queries: {
    queryType: "equality"
  }
}
```

Ứng dụng có thể tìm:

```javascript
await collection.findOne({
  nationalId: "ID-00991"
});
```

với client cấu hình QE đúng.

Các phép so sánh được hỗ trợ ở MongoDB 9.0 cho equality bao gồm `$eq`, `$ne`, `$in`, `$nin` và các tổ hợp logic theo danh sách supported operations. Không phải mọi operator trên field plaintext đều hoạt động với QE.

### 11.2. Không lẫn QE với unique index

Hai document có thể cùng `nationalId:"ID-00991"` mà QE tạo ciphertext khác nhau. **Unique index đặt trên ciphertext encrypted field không bảo đảm uniqueness của plaintext**.

Nếu cần unique business key:

- Đánh giá một **registry** độc lập giữ normalized business key hoặc HMAC token với quản lý khóa phù hợp.
- Cưỡng chế unique trên một trường/collection **có thể index và phân vùng hợp lệ**.
- Quy định tenant scope, canonicalization và idempotency.
- Dùng transaction/atomic state machine phù hợp để phối hợp registry với business document.
- Kiểm soát quyền truy cập registry, vì token/HMAC hoặc khóa lookup có threat model riêng.

Không lưu thẳng SHA-256 không salt của một mã định danh có không gian nhỏ rồi coi đó là bí mật; attacker có thể dictionary-attack. HMAC với secret có lifecycle và rotation rõ giúp bảo vệ tốt hơn trong những kiến trúc lookup tương ứng, nhưng phải được review bảo mật.

### 11.3. Null và field thiếu

QE không hỗ trợ mã hóa BSON `null`/`undefined` theo tài liệu hiện hành. Vì vậy cần phân biệt:

- **Field vắng mặt**: document không có field mã hóa, theo quy tắc schema/client.
- **Giá trị null**: không mặc định được mã hóa như một string.
- **Chuỗi rỗng**: kiểu string nhưng có ý nghĩa nghiệp vụ riêng.
- **Giá trị không đúng BSON type**: có thể gây lỗi encryption/validation.

Nếu nghiệp vụ cần trạng thái “chưa cung cấp”, có thể dùng **không có field**, hoặc metadata trạng thái riêng theo chính sách. Không đặt `nationalId:null` vào field bắt buộc encrypted và kỳ vọng query equality trên null hoạt động.

## 12. QE range: dữ liệu số và ngày

### 12.1. Khả năng từ MongoDB 8.0

Range queries trên QE hỗ trợ BSON types như:

- `date`.
- `int` / `long`.
- `double` / `decimal` theo ràng buộc cụ thể.

Ví dụ cần tìm các hồ sơ có số tiền bảo hiểm trong khoảng:

```javascript
{
  path: "premiumCents",
  bsonType: "long",
  queries: {
    queryType: "range",
    min: Long.fromNumber(0),
    max: Long.fromNumber(1000000000)
  }
}
```

Query:

```javascript
await encryptedCollection.find({
  premiumCents: {
    $gte: Long.fromNumber(20000000),
    $lt: Long.fromNumber(50000000)
  }
}).toArray();
```

Phải dùng **kiểu BSON chính xác**. Trong Node.js, `Long.fromNumber()`/`Long.fromString()` giúp tránh nhập sai `int/double`; với giá trị vượt JS safe integer hãy dùng cách chuyển đổi an toàn.

### 12.2. Bounds có ảnh hưởng bảo mật và hiệu năng

Các tham số `min`, `max` xác định **miền truy vấn đã khai báo**. MongoDB có thể từ chối query vượt bounds.

- Bounds quá rộng có thể làm tăng chi phí index/query.
- Bounds quá hẹp có thể ngăn lưu/truy vấn dữ liệu hợp lệ trong tương lai.
- Với `double/decimal`, cần cấu hình những tham số precision theo phiên bản.
- Range trên dữ liệu nhạy cảm có threat model riêng; query transcripts có thể giúp attacker suy luận trong một số mô hình.

Không chọn min/max chỉ theo dữ liệu tháng hiện tại mà không xét tăng trưởng dài hạn.

### 12.3. Kiểu tiền tệ và precision

Đối với tài chính, nếu có thể, lưu **đơn vị nhỏ nhất bằng số nguyên** (cents/đồng với miền giá trị phù hợp) giúp tránh lỗi float. Khi dùng Decimal128, cần kiểm tra chính xác:
  
- driver hỗ trợ encrypted range cho `decimal` ở phiên bản nào;
- precision/min/max;
- serialization và so sánh;
- dữ liệu không được vượt cấu hình.

Encryption không sửa lỗi chọn kiểu dữ liệu; một khoảng tiền bị làm tròn sai trước encryption vẫn sai sau decryption.

## 13. QE prefix, suffix, substring ở MongoDB 9.0

### 13.1. Bản GA và các phép so khớp

MongoDB 9.0 phát hành GA cho:

- **Prefix:** giá trị bắt đầu bằng một chuỗi; dùng các biểu thức hỗ trợ như `$encStrStartsWith`.
- **Suffix:** giá trị kết thúc bằng một chuỗi; dùng `$encStrEndsWith`.
- **Substring:** chuỗi con nằm bất kỳ trong giá trị; dùng `$encStrContains`.
- **Normalized equality:** khả năng so khớp chuẩn hóa với biểu thức liên quan theo cấu hình.

Đây là **truy vấn QE trên encrypted string fields**, **không phải MongoDB Search `$search`**. Không suy luận hỗ trợ text relevance, stemming, fuzzy hoặc full-text index từ việc có substring query.

### 13.2. Giới hạn độ dài rất quan trọng

Với `substring` ở 9.0:

- Field chuỗi được lập index có **`strMaxLength` từ 2 đến 50** theo cấu hình.
- Chuỗi con được query có độ dài từ **2 đến 6 ký tự** theo các giới hạn `strMinQueryLength`/`strMaxQueryLength` phù hợp.
- Không hỗ trợ query substring dài tùy ý như một regex trên plaintext.
- Các giới hạn này ảnh hưởng storage, write cost, khả năng truy vấn và migration.

Với prefix/suffix, cấu hình độ dài query phải đáp ứng giới hạn của query type và version.

Ví dụ dữ liệu `nationalId` dài ngắn ổn định có thể phù hợp với một số partial-match cases. Trường `internalNote` dài hàng nghìn ký tự **không phải** use case thích hợp cho substring QE có giới hạn 50 ký tự.

### 13.3. Case sensitivity, diacritics và tiếng Việt

Các query type string cho phép cấu hình `caseSensitive` và `diacriticSensitive` theo tài liệu 9.0.

Ví dụ nghiệp vụ muốn `"nguyen"` và `"Nguyễn"` cùng match cần:

1. Xác định đúng mức tương đương Unicode/case/diacritic.
2. Xác định tác động đến false positives.
3. Cấu hình index và query parameters phù hợp **trước khi tạo collection**.
4. Thử với dữ liệu Việt Nam và mã định danh có dấu/không dấu.
5. Không xem collations thông thường là cách tự động sửa mọi phép so trên ciphertext.

**QE không sử dụng collation như một field plaintext thông thường**; server không thể áp collation chung lên ciphertext rồi ra kết quả mong đợi.

### 13.4. Public preview 8.2/8.3 không giống GA 9.0

Theo release notes MongoDB 9.0, kiểu `prefixPreview`/`suffixPreview`/`substringPreview` của các bản public preview **không tương thích trực tiếp** với cơ chế GA mới. Nếu đang ở 8.2/8.3:

- Không thay driver/server rồi chạy trực tiếp mà không lập kế hoạch.
- Kiểm tra cách migrate hoặc tạo collection mới.
- Test decryption/read/write/query với đúng compatibility matrix.
- Đảm bảo có rollback và backup keys/metadata.

Không trộn code snippet cho preview với thư viện 9.0 hiện hành.

## 14. Các giới hạn QE cần đưa vào thiết kế

### 14.1. BSON types

Bảng khái quát theo tài liệu hiện hành:

| Query type | BSON types phù hợp điển hình |
| --- | --- |
| `equality` | Nhiều BSON types thông dụng, **không gồm** array/object/double/decimal |
| `range` | date, int, long, double, decimal |
| `prefix/suffix/substring` | string |
| `none` | Có thể mã hóa array/object nguyên khối, nhưng không query vào bên trong |
| Bị loại ở các query types | null, undefined, MinKey, MaxKey |

Thêm lưu ý: không thể mã hóa field nằm **bên trong phần tử của array** theo cách tùy ý rồi truy vấn nó như field thường. Nếu dùng array/object, hãy đối chiếu khả năng encrypt nguyên field và giới hạn loại dữ liệu.

### 14.2. CRUD và toán tử

Queryable Encryption chỉ hỗ trợ một **tập con** commands/operators. Theo tài liệu hiện hành:

- Không hỗ trợ `updateMany()` hoặc `deleteMany()` trên QE collection theo semantics được liệt kê.
- `bulkWrite` và `findAndModify` có giới hạn riêng.
- Một số phép aggregation và expression không áp dụng lên encrypted fields.
- `$regex` với encrypted field không tự được hỗ trợ như tìm chuỗi plaintext.
- Query so với `null` hoặc giá trị có kiểu không được phép sẽ lỗi.
- `$text`, `$where`, `$jsonSchema` có các giới hạn/bị từ chối khi dùng qua QE automatic client.
- Upsert có hành vi đặc biệt: **encrypted fields trong filter có thể không được chuyển vào insert**; phải lập kế hoạch document insert rõ ràng.

Cần đọc **Supported Operations for Queryable Encryption** của đúng server/driver trước khi chuyển code sang production, không chỉ test insert/findOne.

### 14.3. Collection và index

Tài liệu MongoDB nêu các giới hạn với QE:

- **Chỉ áp dụng lên collection được tạo mới đúng quy trình QE**; không bật QE trực tiếp bằng cách sửa schema của collection đang có dữ liệu rồi kỳ vọng bản ghi cũ tự được encrypt.
- Không đổi `queryType` của encrypted field trên collection hiện hữu.
- Không rename encrypted field hoặc collection theo cách dùng `$rename`/`renameCollection` thông thường.
- Không dùng đồng thời CSFLE và QE trên cùng một collection.
- Không hỗ trợ một số dạng collection như **time-series, capped, views** trong các trường hợp hiện hành.
- **TTL và unique indexes** có giới hạn đặc thù; unique index trên encrypted field **không bảo vệ uniqueness của plaintext**.
- Không tạo index B-tree thường trên encrypted field QE và kỳ vọng nó là index queryable.
- Không xóa/tự tạo metadata collections của QE.

Nhiều trường hợp yêu cầu kiểm tra riêng `__safeContent__` index do driver/collection creation workflow thiết lập.

### 14.4. Sharding, read preference và transactions

Với QE trên sharded cluster, cần xét:

- Topology/FCV và hỗ trợ mongos/shards.
- Khả năng query bằng encrypted field có phù hợp shard key không.
- Unique constraints trên encrypted fields khác uniqueness ở server.
- Giới hạn với secondary reads và một số transaction/CRUD operators.
- Metadata QE có được placement/backup đúng không.
- Migration/resharding có ảnh hưởng encryption metadata không.

Đừng dùng plaintext một mã định danh nhạy cảm làm shard key chỉ để targeted routing mà không đánh giá rủi ro lộ dữ liệu. Cũng đừng mặc định có thể tạo hashed/unique index trên ciphertext và nhận semantics của plaintext.

## 15. Thực hành Queryable Encryption automatic bằng Node.js

### 15.1. Điều kiện nghiêm ngặt trước khi chạy

Ví dụ sau dùng:

- **MongoDB Atlas hoặc Enterprise test deployment** hỗ trợ automatic QE.
- Replica set hoặc sharded cluster tương thích.
- Node.js MongoDB driver + `mongodb-client-encryption` phù hợp.
- **Automatic Encryption Shared Library (`crypt_shared`)** đúng phiên bản và nền tảng.
- Quyền tạo namespace/Key Vault và các metadata collections.
- Local KMS key **chỉ cho lab**, tuyệt đối không dùng production.
- Collection tên riêng mỗi lượt, không ghi đè collection hiện hữu.

Nếu thiếu điều kiện, **không chạy** rồi chỉnh thẳng collection thủ công để “ép QE hoạt động”. Có thể học schema, đọc tài liệu và triển khai sau trên lab đã được cấp quyền.

### 15.2. Mẫu code với equality field

Đặt `MONGODB_URI` và `CRYPT_SHARED_LIB_PATH` theo test environment. Trình tự:

1. Kết nối client quản trị test.
2. Tạo Key Vault với unique index trên alias.
3. Tạo `ClientEncryption`.
4. Tạo QE collection bằng helper `createEncryptedCollection()` để sinh DEK và metadata.
5. Tạo encrypted `MongoClient` có `encryptedFieldsMap`, KMS options và crypt_shared.
6. Thao tác insert/query plaintext ở client; ciphertext sẽ được lưu trên server.

```javascript
const {
  MongoClient,
  ClientEncryption,
  ObjectId
} = require("mongodb");

const { randomBytes } = require("node:crypto");

async function runQueryableEncryptionLab() {
  const uri = process.env.MONGODB_URI;
  const cryptSharedLibPath =
    process.env.CRYPT_SHARED_LIB_PATH;

  if (!uri || !cryptSharedLibPath) {
    throw new Error(
      "Need MONGODB_URI and CRYPT_SHARED_LIB_PATH"
    );
  }

  const admin = new MongoClient(uri);
  await admin.connect();

  let encryptedClient;

  try {
    const dbName = "mongo_encryption_row335_lab";
    const runId = new ObjectId().toHexString();
    const collectionName = "qe_" + runId;
    const keyVaultCollection = "vault_qe_" + runId;
    const keyVaultNamespace =
      dbName + "." + keyVaultCollection;
    const namespace = dbName + "." + collectionName;

    const db = admin.db(dbName);
    const vault = db.collection(keyVaultCollection);

    await vault.createIndex(
      { keyAltNames: 1 },
      { unique: true }
    );

    const kmsProviders = {
      local: {
        key: randomBytes(96)
      }
    };

    const clientEncryption = new ClientEncryption(admin, {
      keyVaultNamespace,
      kmsProviders
    });

    const requestedEncryptedFields = {
      fields: [
        {
          path: "privateCode",
          bsonType: "string",
          queries: { queryType: "equality" }
        },
        {
          path: "privateNote",
          bsonType: "string"
          // encrypt, but not queryable
        }
      ]
    };

    // Helper tạo DEKs và metadata collection đúng cách.
    const created =
      await clientEncryption.createEncryptedCollection(
        db,
        collectionName,
        {
          provider: "local",
          createCollectionOptions: {
            encryptedFields: requestedEncryptedFields
          }
        }
      );

    // created.encryptedFields có keyIds đã sinh.
    const finalEncryptedFields = created.encryptedFields;

    encryptedClient = new MongoClient(uri, {
      autoEncryption: {
        keyVaultNamespace,
        kmsProviders,
        encryptedFieldsMap: {
          [namespace]: finalEncryptedFields
        },
        extraOptions: {
          cryptSharedLibPath
        }
      }
    });

    await encryptedClient.connect();

    const encryptedCollection = encryptedClient
      .db(dbName)
      .collection(collectionName);

    const id = new ObjectId();

    await encryptedCollection.insertOne({
      _id: id,
      runId,
      publicLabel: "Sample QE record",
      privateCode: "DEMO-SECRET-335",
      privateNote: "Chỉ đọc sau khi tìm bằng _id"
    });

    // QE automatic: driver chuyển equality filter.
    const hit = await encryptedCollection.findOne({
      privateCode: "DEMO-SECRET-335"
    });

    if (!hit || !hit._id.equals(id)) {
      throw new Error("QE equality lookup failed");
    }

    // Client thường không có KMS sẽ thấy ciphertext Binary.
    const raw = await admin
      .db(dbName)
      .collection(collectionName)
      .findOne({ _id: id });

    console.log({
      namespace,
      foundByEncryptedEquality: true,
      decryptedCodeMatches:
        hit.privateCode === "DEMO-SECRET-335",
      rawCodeIsBinary:
        raw.privateCode?._bsontype === "Binary",
      rawNoteIsBinary:
        raw.privateNote?._bsontype === "Binary"
    });

    // Không log nội dung nhạy cảm, local key hay DEK.
    // Không drop encrypted collection/metadata trong demo.
  } finally {
    if (encryptedClient) {
      await encryptedClient.close();
    }
    await admin.close();
  }
}

runQueryableEncryptionLab().catch((error) => {
  console.error(error.name, error.message);
  process.exitCode = 1;
});
```

**Giới hạn của demo:** không có quyền tự động xóa các encrypted metadata collections và Key Vault sau khi chạy. Tạo collection lab mới có thể tiêu tốn dung lượng; quản trị viên nên thu hồi **đúng namespace và metadata liên quan** bằng driver QE tương thích, sau khi xác nhận không còn phụ thuộc vào DEK. Không chạy `dropDatabase()`/`drop()` tùy tiện trên database dùng chung.

### 15.3. Giải thích điểm cốt lõi của demo

- `requestedEncryptedFields` là **ý định schema** do ứng dụng khai báo.
- `createEncryptedCollection()` tạo collection đúng quy trình, sinh keyId khi chưa khai báo và thiết lập metadata/index liên quan.
- `encryptedFieldsMap` bảo đảm encrypted client dùng schema đã chọn; không để mọi thứ phụ thuộc vào remote schema chưa kiểm chứng.
- `kmsProviders.local` chỉ là lab, không có backup CMK.
- `cryptSharedLibPath` trỏ tới binary cryptographic/query analysis library hợp lệ.
- `insertOne()` sử dụng plaintext **ở client**, nhưng server nhận ciphertext.
- `findOne({privateCode:...})` chỉ hoạt động nhờ QE query rewrite của client; client không được cấu hình không có khả năng tự query plaintext.
- Raw MongoDB client sẽ nhìn thấy ciphertext, không có quyền tự giải mã.
- Không tạo B-tree index thường trên `privateCode` để “tăng tốc QE”; QE có cơ chế metadata/index riêng.

### 15.4. Nếu helper tạo collection báo lỗi?

Các nguyên nhân thường gặp:

- Server/driver/`crypt_shared` không tương thích.
- Chạy standalone hoặc Community thiếu automatic QE.
- Không có quyền tạo Key Vault/collection/index.
- Không đủ quyền KMS để tạo hoặc unwrap DEK.
- Tên collection/metadata bị trùng với lần thử trước.
- Sai `encryptedFields` schema/BSON type.
- Network/firewall ngăn client gọi KMS.
- Collection được tạo sai quy trình hoặc đã tồn tại.
- Key Vault thiếu unique index cho `keyAltNames`.

Hãy đọc **error code/message**, kiểm tra namespace và quyền. Không sửa ESC/ECOC hoặc `__safeContent__` thủ công để vượt lỗi.

## 16. Bảo vệ schema và quyền truy cập

### 16.1. Tại sao phải kiểm soát schema ở client?

Một client chỉ tin schema lấy từ server có thể gặp rủi ro nếu attacker có quyền thay đổi cấu hình server-side hoặc ứng dụng vô tình dùng sai deployment. Vì vậy, khi phù hợp hãy giữ `schemaMap`/`encryptedFieldsMap` **trong cấu hình được phát hành và kiểm soát** ở application.

Dùng config version và test:

```text
encryptionConfigVersion: enc-v3
collection: people_secure_v3
encryptedFields:
  - nationalId: equality, string
  - incomeCents: range, long
  - internalNote: none, string
```

Không cho hai service writer cùng namespace nhưng một bên encrypt `nationalId` và bên kia ghi plaintext. Nếu có legacy records, cần migration và chặn plaintext writes theo khả năng server/driver.

### 16.2. Encryption không thay RBAC/authorization

Một client có DEK vẫn có thể đọc plaintext field. Do đó cần:

- Người dùng được xác thực.
- Quyền theo tenant, document và mục đích sử dụng.
- Giới hạn decryption role theo service.
- Tách ingestion writer, read service, key admin, database admin.
- Audit KMS decrypt/unwrap, quyền thay đổi key và dữ liệu.
- Không trả ciphertext/decrypted data trong logs, exception, traces.
- Không đặt plaintext trong field `metadata` hay trong `_id` của document mà quên threat model.

Encryption giúp hạn chế ai **có thể đọc plaintext từ database**, nhưng không thay policy “ai được phép gọi API nào”.

### 16.3. KMS IAM và network

Ứng dụng cần quyền đến KMS để unwrap DEK. Một policy production nên:

- Dùng identity ngắn hạn/managed identity thay hardcoded credentials.
- Quyền decrypt/rewrap theo môi trường/collection/tenant cần thiết.
- Tách sandbox và production CMK.
- Giới hạn ai có quyền disable/delete CMK.
- Giám sát KMS failures/throttling.
- Xác định cách xử lý khi KMS unavailable hoặc credential expired.
- Có kế hoạch restore/rotation từ sớm.

Không mã hóa một lần rồi cho rằng KMS sẽ không bao giờ được gọi nữa: client mới, cold cache, key refresh hoặc failover có thể cần unwrap key.

## 17. Key rotation: không phải thao tác đổi một biến môi trường

### 17.1. CMK rotation và DEK rotation khác nhau

**CMK rotation / rewrap:**

- Thay wrapping key trong KMS theo quy trình hỗ trợ.
- DEK có thể được **rewrap** bằng CMK mới, trong khi dữ liệu dùng DEK đó vẫn không cần re-encrypt toàn bộ plaintext.
- Với Node.js có helper `rewrapManyDataKey()` theo driver API tương thích.

**DEK rotation / re-encrypt:**

- Muốn thay DEK thực sự đang mã hóa field, phải thiết kế cách đọc ciphertext cũ, decrypt bằng key cũ và mã hóa lại bằng DEK mới, với quá trình migration/validation phù hợp.
- QE có metadata truy vấn gắn với encrypted collection/key; không thể tùy ý đổi keyId trên schema cũ rồi kỳ vọng toàn bộ dữ liệu/query tokens tự cập nhật.

Không coi việc đổi ARN CMK hoặc xóa DEK cũ là “rotation thành công”.

### 17.2. Runbook rewrap khái niệm

```text
Inventory: CMKs, DEKs, collections, keyAltNames
                    |
       Create/authorize new CMK
                    |
          Rewrap DEKs as supported
                    |
         Validate decrypt with clients
                    |
         Keep old CMK during retention
                    |
         Backup + restore test
                    |
      Retire old material only if safe
```

Tài liệu cho biết `rewrapManyDataKey()` thay lớp CMK wrap, **không thay giá trị DEK**. Một CMK cũ vẫn có thể được cần bởi các DEK, snapshots hoặc dữ liệu archived chưa rewrap.

### 17.3. Rotation và quyền xóa dữ liệu

Nếu xóa CMK/DEK nhằm “cryptographic erasure”, cần review nghiêm ngặt:

- Mất khóa có thể làm không thể đọc lại dữ liệu hợp lệ.
- Dữ liệu có thể đã được giải mã/copy vào cache/log.
- Backups cũ có thể cần key lịch sử.
- Yêu cầu pháp lý có thể đòi retention.
- Các hệ thống bên ngoài có thể giữ plaintext.

Không tự hủy khóa hàng loạt như một cách xử lý định kỳ vô hại.

## 18. Backup, restore và migration

### 18.1. Backup cần đủ các thành phần liên quan

Với CSFLE:

- Business collection ciphertext.
- Key Vault chứa wrapped DEKs.
- CMK còn khả dụng qua KMS.
- Schema config/driver version.

Với QE bổ sung:

- Main encrypted collection.
- ESC và ECOC metadata collections liên quan.
- `__safeContent__` do server/driver quản lý.
- Encrypted fields definition/metadata.
- KMS/Key Vault và driver compatibility.

Chỉ restore main collection nhưng bỏ các QE metadata collections có thể khiến **encrypted queries không đúng**, ngay cả khi vẫn còn ciphertext trong main collection.

### 18.2. Không bật QE bằng cách sửa schema cũ

Một lỗi phổ biến:

```text
Existing collection:
  1,000,000 plaintext documents

Developer:
  add encryptedFieldsMap to client

Expectation:
  old 1,000,000 docs become encrypted automatically
```

Điều này **không xảy ra**. Nếu client mới encrypt các ghi sau đó, collection có thể chứa trộn plaintext và ciphertext. Queries được encrypt theo QE không tự match các old plaintext records.

Phương án migration có kiểm soát:

1. Thiết kế encrypted schema và query needs.
2. Tạo **collection QE mới** bằng driver/helper đúng.
3. Chọn retention, uniqueness và quyền truy cập.
4. Đọc bản ghi nguồn qua đường được kiểm soát.
5. Validate/normalize đúng BSON types.
6. Ghi từng document/batch thích hợp sang collection mới bằng encryption-enabled client.
7. Theo dõi progress, errors, count và samples có quyền.
8. Có chiến lược đồng bộ writes trong thời gian migration (quiesce/dual-write/outbox có kiểm soát).
9. Chuyển read/write traffic theo feature flag/cutover plan.
10. Giữ rollback và không xóa keys/metadata cũ trước khi xác nhận.

**Không** coi đây là một `updateMany({$set:{...}})` đơn giản: QE có limits với multi-document update, schema thay đổi và metadata.

### 18.3. Không migration QE bằng raw copy ciphertext

Nếu copy BinData ciphertext của một encrypted collection sang collection khác mà không tạo/rebuild metadata tương ứng, **queryable index của collection đích có thể không có trạng thái cần thiết**.

Migration phải dùng workflow được MongoDB hỗ trợ; thường cần **decrypt ở client được cấp quyền rồi re-encrypt vào collection mới** với đúng schema/key. Bảo vệ dữ liệu rõ trong suốt quá trình, không ghi plaintext vào staging file hoặc logs.

### 18.4. Không đổi type/queryType tại chỗ

Với QE, query type của field là thiết kế collection lúc tạo. Muốn từ `equality` sang `range` hoặc thêm partial-match cần **xem kế hoạch migrate**, không chỉ sửa một object cấu hình rồi bắt client restart.

## 19. Metadata compaction và chi phí QE

### 19.1. Vì sao ESC/ECOC lớn dần?

QE cần theo dõi thông tin phục vụ truy vấn encrypted fields. Các writes làm metadata collections tăng. Ví dụ đơn giản:

```text
main collection:
   1 document chứa 2 queryable encrypted fields

QE metadata:
   additional entries/writes trong ESC và ECOC
```

Một insert/updated encrypted field có chi phí khác so với plain MongoDB insert. Càng nhiều field queryable, chi phí càng lớn.

### 19.2. Compaction là công việc quản trị có điều kiện

MongoDB hỗ trợ **compaction/cleanup metadata có cấu trúc** để kiểm soát kích thước ESC/ECOC theo quy trình chuyên dụng. Nó có điều kiện về version, quyền, encrypted client và ảnh hưởng hiệu năng.

Không chạy:

```javascript
// NGUY HIỂM: phá metadata QE.
db.getCollection("enxcol_.people.esc").deleteMany({});
db.getCollection("enxcol_.people.ecoc").drop();
```

Thay vào đó:

- Theo dõi kích thước ESC/ECOC.
- Tham khảo tài liệu `compactStructuredEncryptionData` và các phương thức quản trị QE đúng version.
- Lên lịch ngoài giờ cao điểm khi có impact.
- Backup/validate trước và sau.
- Đảm bảo quyền tới KMS và kết nối có encryption config.
- Không tự chạy các command khi không rõ semantics/release.

### 19.3. Compaction cũng có trade-off bảo mật

Tài liệu MongoDB mô tả trong mô hình threat nhất định, compaction có thể tiết lộ thông tin thống kê về các tổ hợp field/value trong khoảng thời gian giữa các đợt. Do đó lịch compaction phải xét **mục tiêu storage/performance và threat model**, không chỉ đặt cron càng thường xuyên càng tốt.

### 19.4. Các tham số tối ưu

Với QE có thể gặp:

- `contention`: cân bằng throughput ghi của các giá trị lặp với hiệu năng find.
- `min/max/precision` của range: quyết định bounds và chi phí.
- `sparsity/trimFactor`: tham số nâng cao theo loại query/version.
- `strMaxLength`/`strMinQueryLength`/`strMaxQueryLength` cho partial string.

Không copy các giá trị tuning từ một blog cũ sang production mà không đo. Những tham số này có thể ảnh hưởng security/performance và tạo ra schema/index khác nhau; nhiều cấu hình không thể sửa đơn giản sau khi collection đã có dữ liệu.

## 20. Đánh giá hiệu năng, khả năng mở rộng và monitoring

### 20.1. Baseline trước khi bật encryption

Đo trên workload đại diện:

| Metric | Vì sao quan trọng |
| --- | --- |
| p50/p95/p99 insert latency | Có overhead key access và QE metadata writes không? |
| p50/p95/p99 equality/range query | Kiểu query nào tạo chi phí lớn? |
| Query throughput/QPS | Có đủ capacity sau khi encrypt? |
| CPU tại client | Crypto/query analysis không miễn phí |
| CPU/disk/network ở MongoDB | Dữ liệu mã hóa và metadata tăng tải |
| KMS request rate/latency | Cold key cache và network có ảnh hưởng? |
| Key unwrap failures | Lỗi quyền/availability KMS |
| ESC/ECOC size growth | Có cần compaction/sizing? |
| Write conflict/timeout | Dữ liệu low-cardinality có gây contention? |
| Memory/driver pool | Có tăng kết nối/cache/CPU tại service? |
| Backup/restore duration | Extra metadata, keys và dữ liệu đã lớn hơn? |

Không nói “QE chậm hơn X%” nếu không có benchmark với corpus, query types và topology cụ thể.

### 20.2. Lưu ý query diagnostics bị redacted

MongoDB QE **redact/omit** một số thông tin trong query logs, profiler và diagnostic commands để tránh lộ thông tin. Vì vậy:

- Một số query không xuất hiện trong profiler như plain MongoDB.
- `collStats`, `currentOp` và output liên quan có thể bị lược/redacted.
- Đội vận hành nên có **application-level APM metrics** theo operation, loại query, tenant tier và index version, không log raw plaintext.
- Không tìm cách tắt redaction hoặc đưa plaintext query vào logs chỉ để debug dễ hơn.

### 20.3. Trace an toàn

Một record minh họa:

```json
{
  "traceId": "tr-335",
  "collection": "people_secure",
  "operation": "encrypted-equality-lookup",
  "queryClass": "national-id-exact",
  "success": true,
  "latencyMs": 85,
  "kmsLatencyMs": 12,
  "keyAliasClass": "tenant-level"
}
```

Không log national ID, encrypted payload, raw query tokens, key material, full encrypted schema có secrets hoặc KMS credentials. Ngay cả ciphertext/query transcript cũng có thể nhạy cảm trong một số threat model.

### 20.4. Công suất metadata

Số field queryable và số lần insert/update có thể làm ESC/ECOC tăng nhanh. Tránh:

- encrypt/query mọi field chỉ vì “an toàn hơn”;
- dùng range cho field chỉ cần equality;
- dùng substring cho mô tả dài;
- dùng low-cardinality queryable field với write hotspot quá lớn mà không cân nhắc `contention`;
- chạy bulk migration ở tốc độ tối đa khi chưa sizing ESC/ECOC.

## 21. Những lỗi thường gặp và cách điều tra

### 21.1. Không decrypt được một field

Các khả năng:

- Sai KMS/CMK hoặc credential expired.
- Key Vault namespace sai.
- Key ID cần thiết đã bị xóa.
- Key Vault chưa restore cùng dữ liệu.
- Driver/encryption library mismatch.
- Client đang dùng encryption schema không phù hợp.
- Dữ liệu/ciphertext bị sửa hoặc corruption.
- Network KMS bị chặn.

Không giải quyết bằng cách in CMK/DEK ra logs hoặc disable encryption. Kiểm tra error code, đúng namespace/keyId, KMS audit và khôi phục credentials.

### 21.2. QE find trả rỗng dù MongoDB có document

Cần kiểm tra:

1. Dữ liệu được insert qua encrypted client hay raw client?
2. Collection QE có được tạo đúng quy trình trước khi insert?
3. `encryptedFieldsMap` có khớp definition/server?
4. Query type của field có hỗ trợ operator đang dùng?
5. Query input có đúng BSON type?
6. Trường encrypted có null/missing không?
7. Có filter tenant/status loại document không?
8. ESC/ECOC/`__safeContent__` có từng bị chỉnh sửa không?
9. Driver/crypt_shared/FCV có tương thích?
10. Có replication/cutover/migration đang diễn ra không?

Không coi ciphertext không match plaintext là lỗi MongoDB query engine.

### 21.3. “Duplicate” trên nationalId đã encrypt

Nếu QE uses randomized ciphertext, unique index trên trường đó **không đảm bảo plaintext unique**. Xử lý bằng kiến trúc business key registry/hợp đồng uniqueness trước khi deploy.

### 21.4. Ghi encrypted field lỗi schema

Có thể:

- Field có kiểu BSON không được mã hóa.
- String/number type khác schema.
- Query ngoài range bounds.
- `null`/`undefined` không hợp lệ.
- Partial string vượt configured length.
- Collection có encryptedFields query type khác client.
- Đang dùng một operator update không được hỗ trợ.

Không sửa field ciphertext thủ công. Điều chỉnh contract dữ liệu hoặc migrate collection theo chính sách.

### 21.5. Thay encrypted schema nhưng kết quả sai

Tài liệu MongoDB cảnh báo thay `encryptedFieldsMap` trên existing collection có thể tạo **document cũ plaintext, document mới encrypted** và queries không nhất quán. Giải pháp là rollback cấu hình/migration có kiểm soát, không thêm tiếp một cấu hình tạm “bỏ mã hóa” chỉ để query ra dữ liệu.

### 21.6. KMS outage

Khi KMS không sẵn sàng:

- Một số client có cached DEKs có thể tiếp tục trong phạm vi cache/lifecycle.
- Client khởi động mới hoặc cần key chưa cached có thể lỗi.
- Tỷ lệ lỗi decrypt/encrypt tăng.
- Retry phải có backoff, không tạo “thundering herd” vào KMS.
- Không bật fallback lưu plaintext để giữ ứng dụng chạy.

Đặt circuit breaker/observability và degraded mode an toàn, ví dụ chỉ cho các API không chạm encrypted fields tiếp tục.

## 22. Quy trình triển khai production

### 22.1. Phân loại dữ liệu trước

Tạo bản đồ trường:

| Field | Nhạy cảm? | Query cần hỗ trợ | Hướng cân nhắc |
| --- | --- | --- | --- |
| `_id` kỹ thuật | Không chứa PII | Tra theo ID | Để thường, ID ngẫu nhiên |
| `tenantId` | Có thể nhạy cảm về tổ chức | Authorization filter | Đánh giá leakage, có thể để thường với access control |
| `nationalId` | Rất nhạy cảm | Exact lookup | QE equality hoặc kiến trúc lookup được review |
| `incomeCents` | Nhạy cảm | Khoảng giá trị | QE range trên MongoDB phù hợp |
| `internalNote` | Rất nhạy cảm | Không query nội dung | CSFLE randomized hoặc QE none |
| `status` | Cardinality thấp | Filter thường xuyên | Tránh CSFLE deterministic theo thói quen; phân tích threat |
| `updatedAt` | Metadata vận hành | Sort/time window | Cân nhắc không encrypt hoặc thiết kế range QE nếu thực sự cần |

Điều quan trọng: **để field plaintext** là một quyết định có kiểm soát khi cần query/sort, không phải mặc định mọi field đều có cùng mức nhạy cảm.

### 22.2. Preflight

- Thống nhất threat model và regulatory requirements.
- Chọn CSFLE hay QE từng collection (không mix hai công nghệ trên cùng collection).
- Xác định query types và BSON type của từng field.
- Kiểm tra version/FCV/driver/crypt_shared/edition.
- Chọn remote KMS, IAM, region, recovery và key rotation.
- Thiết kế Key Vault riêng, quyền và unique alias index.
- Kiểm tra unique business invariants độc lập.
- Lập test compatibility cho mọi API read/write/update/upsert/bulk/aggregation.
- Tính storage/CPU/network/KMS capacity và backup.
- Thiết kế migration nếu collection đã có dữ liệu.

### 22.3. Staging

- Dùng dữ liệu giả/ẩn danh có phân phối đại diện.
- Tạo encrypted collection mới qua helper/driver hỗ trợ.
- Đo equality/range/partial-match latency.
- Thử trường missing/null/wrong BSON type.
- Thử KMS credential expired, client restart, primary failover.
- Thử key vault restore và decrypt qua client được cấp quyền.
- Chạy negative tests cho raw client/unauthorized tenant.
- So số bản ghi và business keys trước/sau migration.
- Xác minh **không có plaintext** trong raw document của encrypted field.

### 22.4. Rollout

```text
Design fields + queries + KMS
             |
             v
Provision Key Vault + roles
             |
             v
Create new encrypted collection
             |
             v
Migrate / backfill carefully
             |
             v
Shadow reads + consistency checks
             |
             v
Canary traffic / feature flag
             |
             v
Monitor latency, correctness, KMS
             |
             v
Cutover
             |
             v
Retain old data/keys for rollback
             |
             v
Retire only after review
```

Nếu canary lỗi, rollback phải đưa **cả config encryptedFields/query templates và data routing** về trạng thái tương thích. Không chỉ đổi tên collection rồi tưởng đã đủ.

### 22.5. Incident response

Nếu phát hiện lộ plaintext hay secret:

1. Cô lập đường rò rỉ và khóa phạm vi truy cập.
2. Xác định dữ liệu, keys, query logs và services bị ảnh hưởng.
3. Ngăn client/kẻ tấn công tiếp tục sử dụng compromised credentials.
4. Đánh giá key rotation/migration phù hợp, không hủy keys ngay làm mất dữ liệu.
5. Khôi phục dịch vụ bằng IAM/key material an toàn.
6. Reconcile dữ liệu và audit access.
7. Thực hiện quy trình thông báo/tuân thủ nếu áp dụng.
8. Bổ sung tests và phòng ngừa lặp lại.

Đừng chỉ gọi `rewrapManyDataKey()` rồi kết luận đã an toàn nếu **DEK/plaintext hoặc application process** bị lộ. Rewrap CMK không thay DEK và không xóa bản plaintext đã bị lấy.

## 23. Những nhầm lẫn cần tránh

| Nhầm lẫn | Điều đúng |
| --- | --- |
| “TLS bảo vệ dữ liệu khỏi DBA đọc” | TLS chỉ bảo vệ đường truyền; DBA có quyền có thể đọc plaintext field nếu không dùng client-side encryption |
| “Encryption at rest bằng CSFLE” | Là các lớp khác nhau, có thể bổ sung cho nhau |
| “CSFLE deterministic không có leakage” | Cùng plaintext tạo cùng ciphertext, có rủi ro frequency analysis |
| “CSFLE randomized vẫn `find({secret:value})` được” | Không, không query trực tiếp theo giá trị random encrypted field |
| “QE ciphertext khác nhau nên không query được” | QE dùng cấu trúc encrypted queryable index và giao thức riêng |
| “QE hỗ trợ mọi MongoDB operator” | Chỉ tập con theo query type/server/driver |
| “MongoDB 7.0 có QE range GA” | Range cần MongoDB 8.0 trở lên |
| “Prefix/suffix/substring GA ở 8.2” | Public Preview 8.2/8.3 khác GA 9.0 |
| “QE substring là full-text search” | Chuỗi ngắn theo giới hạn, không thay Search relevance |
| “Có QE thì vẫn tạo unique index trên secret field để chống trùng” | Randomized ciphertext không cưỡng chế plaintext uniqueness |
| “Chỉ cần thêm `encryptedFieldsMap` vào collection có dữ liệu cũ” | Không tự migrate old documents |
| “Có thể đổi query type trên collection đang chạy” | Query type không thay tùy ý; cần migration |
| “Dùng QE và CSFLE cùng collection cho chắc” | Tài liệu QE không hỗ trợ mix hai công nghệ trên cùng collection |
| “Xóa ESC/ECOC để tiết kiệm dung lượng” | Có thể làm sai encrypted queries hoặc phá dữ liệu |
| “Compaction metadata giống `deleteMany`” | Phải dùng lệnh QE chuyên dụng |
| “DEK được lưu rõ trong MongoDB” | Key Vault lưu DEK được CMK wrap |
| “Có backup data là đủ” | Cần backup Key Vault và khả năng khôi phục CMK |
| “Rotate CMK tự đổi DEK trên mọi bản cũ” | CMK rotation/rewrap khác DEK re-encryption |
| “Không có KMS thì fallback plaintext tạm” | Vi phạm security requirement; cần fail safely |
| “Encryption thay thế authorization” | Client có khóa vẫn phải kiểm quyền tenant/document |
| “QE logs/profiler giống plaintext collection” | Một số diagnostics bị redacted/omitted |
| “Mọi trường encrypted đều nên indexed” | Queryable fields tăng chi phí và leakage trade-off |
| “Query trên encrypted field dùng collation bình thường” | QE có hạn chế collation, string query có cấu hình riêng |
| “Thử nghiệm với local key có thể dùng production” | Production cần remote KMS và quản trị khóa an toàn |

## 24. Bài tập thiết kế và tự luyện

### Bài A. Chọn kỹ thuật phù hợp

Một ứng dụng lưu:

```javascript
{
  taxId: "...",
  countryCode: "VN",
  creditLimitCents: NumberLong("350000000"),
  privateMemo: "...",
  tenantId: "T1"
}
```

Yêu cầu:

1. Tra chính xác theo `taxId`.
2. Tìm theo `creditLimitCents` trong khoảng.
3. Hiển thị `privateMemo` khi mở document, không tìm theo nội dung.
4. Lọc theo tenant, kiểm quyền chặt.
5. Có hàng triệu bản ghi và một số field cardinality thấp.

Hãy chọn CSFLE deterministic/randomized hoặc QE query type phù hợp cho từng field. Giải thích trade-off security/performance/uniqueness và MongoDB version tối thiểu.

### Bài B. Frequency analysis

Một field `riskLevel` chỉ có `LOW` và `HIGH`, 95% dữ liệu là LOW.

- Vì sao deterministic CSFLE có rủi ro?
- Có nên mã hóa randomized nếu ứng dụng không cần query theo riskLevel?
- Nếu cần filter trên field này, cần phân tích threat model và hiệu năng ra sao?
- QE có loại bỏ mọi thông tin rò rỉ trong mọi trường hợp không?

### Bài C. CMK, DEK và Key Vault

Hãy vẽ sơ đồ:

```text
Remote KMS -> CMK -> wrapped DEK in Key Vault
                          |
                          v
                   encrypted field
```

Giải thích hậu quả của:

- Mất CMK.
- Xóa nhầm DEK.
- Backup chỉ main collection mà không có Key Vault.
- Đổi CMK nhưng chưa rewrap các DEK cũ.
- Client có KMS credentials nhưng không được phép đọc collection.

### Bài D. Equality và uniqueness

Hai document cùng plaintext `taxId` được ghi bằng QE equality:

- Ciphertext có bắt buộc giống nhau không?
- Unique index trên encrypted field có bảo đảm business uniqueness không?
- Có thể dùng registry/khóa tra cứu được bảo vệ như thế nào?
- Vì sao dùng raw SHA-256 của một ID dễ đoán lại có rủi ro?

### Bài E. Query type theo phiên bản

Đội ứng dụng đang dùng MongoDB 7.0 và muốn:

1. Equality trên encrypted string.
2. Range trên encrypted income.
3. Substring query trên encrypted string dài 200 ký tự.

Hãy chỉ ra yêu cầu nào có thể triển khai ngay, yêu cầu nào cần nâng cấp/thiết kế lại, và vì sao substring QE 9.0 có giới hạn độ dài.

### Bài F. Migrate collection cũ

`people` hiện có 1 triệu document plaintext. Một developer đề xuất thêm `encryptedFieldsMap` rồi restart app.

- Chuyện gì xảy ra với document cũ?
- Tại sao encrypted equality query có thể bỏ sót document?
- Thiết kế migration sang `people_encrypted_v2` như thế nào?
- Có cần bảo toàn `_id`, uniqueness, references và backup không?
- Làm sao tránh window bị mất ghi trong cutover?

### Bài G. Key rotation

Một tổ chức muốn thay CMK hàng năm.

- Phân biệt KMS rotation và `rewrapManyDataKey()`.
- Sau rewrap, có cần mã hóa lại toàn bộ dữ liệu ngay không?
- Nếu attacker lấy được plaintext DEK, chỉ rewrap bằng CMK mới có đủ không?
- Tại sao cần giữ quyền giải mã snapshot/backup cũ?
- Những người nào nên được cấp quyền quản trị khóa?

### Bài H. Metadata và performance

Một collection có 3 QE fields, số insert gấp 10 lần sau chiến dịch marketing; ESC/ECOC tăng nhanh.

- Vì sao số writes tăng?
- Cần đo những metric nào?
- Khi nào cân nhắc metadata compaction?
- Vì sao không được `drop()` ESC/ECOC?
- Các tham số `contention`/range bounds có thể ảnh hưởng như thế nào?

### Bài I. Tình huống bảo mật ứng dụng

Một service được cấp KMS decrypt và có thể đọc toàn bộ collection. Một API nhận `tenantId` từ query string và trả dữ liệu đã decrypt.

- Encryption có tự ngăn lộ dữ liệu giữa tenants không?
- Cần đặt authorization ở đâu?
- Thông tin nào không nên log?
- Vì sao nên tách role đọc ciphertext và role decrypt?

### Bài J. Truy vấn không hỗ trợ

Một developer muốn chạy:

```javascript
await encryptedCollection.updateMany(
  { nationalId: { $regex: /^ID-/ } },
  { $set: { flag: true } }
);
```

- Vấn đề nào liên quan QE operators?
- Vấn đề nào liên quan multi-document updates?
- Vì sao không được cố gắng sửa ciphertext thủ công?
- Thiết kế thay thế có quyền và lưu lượng kiểm soát ra sao?

### Bài K. QE preview và GA

Một môi trường dùng QE `substringPreview` trên MongoDB 8.3, muốn nâng server lên 9.0.

- Vì sao không coi đây là một minor upgrade tương thích hoàn toàn?
- Cần đọc tài liệu migration nào?
- Khi nào chọn tạo encrypted collection mới?
- Cần test decrypt, query, KMS/driver và rollback ra sao?

### Bài L. Sự cố mất KMS

Một vài ứng dụng vẫn query được do cache, nhưng các pod vừa restart liên tục lỗi decrypt.

- Vì sao có thể xảy ra khác biệt?
- Metric nào giúp nhận diện lỗi KMS?
- Vì sao fallback plaintext bị cấm?
- Làm sao phục hồi mà không log key material hoặc mất dữ liệu?

## 25. Tài liệu chính thức và ghi chú áp dụng

Các khả năng mã hóa rất nhạy với phiên bản server, driver, cryptographic library và KMS. Đối chiếu tài liệu gốc trước khi triển khai:

- [Client-Side Field Level Encryption](https://www.mongodb.com/docs/manual/core/csfle/) — giới thiệu CSFLE, automatic/explicit và compatibility.
- [CSFLE Encryption Algorithms](https://www.mongodb.com/docs/manual/core/csfle/fundamentals/encryption-algorithms/) — deterministic và randomized, rủi ro frequency analysis.
- [CSFLE Encryption Schemas](https://www.mongodb.com/docs/manual/core/csfle/fundamentals/create-schema/) — cách khai báo encryption rules.
- [Queryable Encryption Overview](https://www.mongodb.com/docs/manual/core/queryable-encryption/) — kiến trúc và thành phần.
- [Choosing an In-Use Encryption Approach](https://www.mongodb.com/docs/manual/core/queryable-encryption/about-qe-csfle/) — so sánh CSFLE và QE.
- [Queryable Encryption Supported Operations](https://www.mongodb.com/docs/manual/core/queryable-encryption/reference/supported-operations/) — chính xác operators, BSON types, CRUD và aggregation.
- [Queryable Encryption Limitations](https://www.mongodb.com/docs/manual/core/queryable-encryption/reference/limitations/) — topology, unique/TTL, migration, diagnostics redaction, threat model.
- [Queryable Encryption Schema](https://www.mongodb.com/docs/manual/core/queryable-encryption/qe-create-encryption-schema/) — `encryptedFields`, query type, bounds và partial-match config.
- [Create Encrypted Collection](https://www.mongodb.com/docs/manual/core/queryable-encryption/qe-create-encrypted-collection/) — quy trình tạo collection và insert.
- [Query Encrypted Data](https://www.mongodb.com/docs/manual/core/queryable-encryption/qe-retrieve-encrypted-document/) — equality/range và truy vấn mới theo version.
- [Encryption Keys and Key Vaults](https://www.mongodb.com/docs/manual/core/queryable-encryption/fundamentals/keys-key-vaults/) — CMK, DEK, Key Vault, rewrap.
- [Manage Encrypted Collections and Metadata](https://www.mongodb.com/docs/manual/core/queryable-encryption/fundamentals/manage-collections/) — ESC, ECOC, `__safeContent__` và compaction.
- [Queryable Encryption Quick Start](https://www.mongodb.com/docs/manual/core/queryable-encryption/quick-start/) — lab tương thích và cảnh báo local key.
- [MongoDB 9.0 Compatibility](https://www.mongodb.com/docs/manual/release-notes/9.0-compatibility/) — migration từ prefix/suffix/substring preview 8.2/8.3 sang GA.
- [Node.js Driver ClientEncryption API](https://mongodb.github.io/node-mongodb-native/) — kiểm tra signature `encrypt()`, `createDataKey()`, `createEncryptedCollection()` và `rewrapManyDataKey()` cho driver đang dùng.

**Ghi chú phiên bản tại thời điểm viết:** MongoDB 9.0 hiện có prefix/suffix/substring QE GA; ví dụ này không nhằm thay thế documentation/version matrix của deployment cụ thể. Đặc biệt, chính sách edition và availability của automatic encryption phải được kiểm tra theo môi trường Atlas/Enterprise và driver.

## 26. Kết luận

**CSFLE** và **Queryable Encryption** giúp mã hóa các field nhạy cảm **trước khi dữ liệu rời application**, bổ sung cho TLS, encryption at rest, authentication và authorization. CSFLE deterministic hỗ trợ equality nhưng có thể lộ pattern trùng/frequency; CSFLE randomized giảm dấu vết này nhưng không query theo giá trị field. QE dùng randomized ciphertext cùng encrypted metadata/index để hỗ trợ các kiểu truy vấn có điều kiện, gồm equality, range và partial string ở các phiên bản mới, đổi lại là **chi phí storage, write, quản trị khóa và giới hạn operations**.

Sử dụng đúng công nghệ đòi hỏi một thiết kế đầy đủ: **threat model → chọn field/BSON type/query type → remote KMS/CMK/DEK/Key Vault → tạo encrypted collection đúng cách → API authorization và uniqueness → migration/backup/rotation → monitoring và khôi phục**. Không dùng encryption như thay thế cho phân quyền; không sửa trực tiếp ESC/ECOC/`__safeContent__`; không xóa khóa khi còn dữ liệu phụ thuộc; và không suy luận mọi thao tác MongoDB plaintext đều được phép trên ciphertext.

**Thông điệp cốt lõi:** mã hóa tại client chỉ thực sự bảo vệ dữ liệu khi **khóa, schema, quyền truy cập, quy trình ghi–đọc và khả năng khôi phục** đều được thiết kế nhất quán.
