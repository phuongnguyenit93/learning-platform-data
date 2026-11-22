# Phân tích cửa sổ với $setWindowFields: xếp hạng và tổng lũy kế trong MongoDB

## Mục tiêu bài học

Các báo cáo nghiệp vụ thường cần trả lời những câu hỏi mà `$group` đơn thuần chưa diễn đạt tiện lợi:

- Một cửa hàng đang có **doanh thu lũy kế** bao nhiêu tính đến từng giao dịch?
- Một nhân viên đang đứng **hạng mấy trong cửa hàng** theo doanh thu?
- Nếu hai nhân viên bằng điểm, nên cùng hạng hay vẫn cần một **số thứ tự duy nhất**?
- Trung bình doanh thu của **ba giao dịch gần nhất** là bao nhiêu?
- Doanh thu của **hai ngày gần nhất** khác gì với hai giao dịch gần nhất?
- Mỗi dòng đóng góp bao nhiêu phần trăm vào **tổng doanh thu toàn nhóm**?

MongoDB cung cấp aggregation stage **`$setWindowFields`** từ phiên bản **5.0** để tính toán trên một tập document lân cận hoặc cùng nhóm, gọi là **window**, đồng thời vẫn giữ từng document ở đầu ra. Đây là công cụ quan trọng của **Aggregation nâng cao** cho dashboard, báo cáo theo thời gian, bảng xếp hạng và các phân tích chuỗi dữ liệu.

Bài tập trung vào hai nhóm ứng dụng:

1. **Xếp hạng** bằng `$rank`, `$denseRank` và `$documentNumber`.
2. **Tổng lũy kế** bằng `$sum` với cửa sổ từ đầu partition đến document hiện tại.

Sau bài học, bạn có thể:

- Đọc và viết đúng cấu trúc `partitionBy`, `sortBy`, `output` và `window`.
- Phân biệt **partition**, **thứ tự trong partition** và **phạm vi window**.
- Hiểu xếp hạng có **khoảng trống**, xếp hạng **liền mạch**, và số dòng **không trùng**.
- Tính running total, running count, moving average, tổng toàn partition và tỷ trọng.
- Phân biệt cửa sổ theo **số document** với cửa sổ theo **giá trị hoặc thời gian**.
- Xử lý các dòng trùng timestamp, giá trị missing/null, sai kiểu BSON và thứ tự không ổn định.
- Tổ chức pipeline đúng để lọc dữ liệu mà không vô tình làm sai tích lũy.
- Đánh giá chi phí sort, memory, disk spill và index, rồi áp dụng trong mongosh hoặc Java Driver.

> **Điểm mấu chốt:** `$group` thường **gom nhiều document thành một dòng đại diện** cho nhóm. `$setWindowFields` **giữ mỗi document**, thêm kết quả được tính trên phần dữ liệu liên quan đến document đó.

---

## 1. Vì sao cần phân tích cửa sổ?

### 1.1. Câu hỏi tổng nhóm và câu hỏi trên từng dòng

Giả sử ba giao dịch của cửa hàng HCM:

| Giao dịch | Ngày | Doanh thu |
|---|---|---:|
| A | 01/01 | 100 |
| B | 02/01 | 200 |
| C | 03/01 | 50 |

Muốn tìm **tổng doanh thu của HCM**, `$group` rất phù hợp:

~~~javascript
db.sales.aggregate([
  {
    $group: {
      _id: "$store",
      totalRevenue: { $sum: "$revenue" }
    }
  }
]);
~~~

Kết quả cho HCM: một document chứa `totalRevenue: 350`.

Nhưng nếu cần kết quả dạng:

| Giao dịch | Doanh thu dòng | Doanh thu lũy kế đến dòng |
|---|---:|---:|
| A | 100 | 100 |
| B | 200 | 300 |
| C | 50 | 350 |

thì phải **giữ nguyên các dòng** và tính tổng từ đầu đến từng dòng. `$setWindowFields` biểu diễn trực tiếp yêu cầu này.

### 1.2. Sơ đồ tư duy

~~~text
Collection sales
        |
        v
      $match            chọn phạm vi dữ liệu muốn phân tích
        |
        v
  $setWindowFields
     partitionBy        chia theo cửa hàng/khách/nhân viên...
     sortBy             xác định thứ tự trong từng nhóm
     output.window      xác định các dòng được nhìn thấy
     output.operator    $sum, $avg, $rank, $denseRank...
        |
        v
      $sort             xác định thứ tự trả kết quả
        |
        v
     $project           chọn field cho báo cáo/API
~~~

Không được lẫn lộn ba khái niệm:

- **Partition:** nhóm document có cùng giá trị phân vùng.
- **Sort:** thứ tự để tính toán trong mỗi partition.
- **Window:** số/phạm vi document được xét cho **document hiện tại**.

Một partition có thể có 10.000 document, còn window của một dòng chỉ có 3 document gần nó, hoặc toàn bộ 10.000 document tùy khai báo.

---

## 2. Cú pháp tổng quát của `$setWindowFields`

~~~javascript
db.collectionName.aggregate([
  {
    $setWindowFields: {
      partitionBy: "$groupField",
      sortBy: {
        orderField: 1
      },
      output: {
        newField: {
          $sum: "$numericField",
          window: {
            documents: ["unbounded", "current"]
          }
        }
      }
    }
  }
]);
~~~

Ý nghĩa:

| Thành phần | Vai trò | Bắt buộc? |
|---|---|---|
| `partitionBy` | Biểu thức chia các document thành những nhóm độc lập | Tùy chọn; bỏ qua nghĩa là một partition cho toàn bộ input |
| `sortBy` | Các khóa sort và chiều `1`/`-1` trong partition | Bắt buộc với rank/order operators và bounded windows; không bắt buộc trong mọi trường hợp |
| `output` | Định nghĩa những field được thêm vào mỗi document | Bắt buộc |
| `$sum`, `$avg`, `$rank`... | Window operator được dùng để tính giá trị | Theo từng output field |
| `window` | Phạm vi dữ liệu cho operator hỗ trợ explicit window | Có thể bỏ qua với một số operator; rank operators không nhận `window` |
| `documents` | Biên cửa sổ theo vị trí dòng | Một kiểu window |
| `range` | Biên cửa sổ theo giá trị của trường sắp xếp | Một kiểu window |
| `unit` | Đơn vị thời gian cho time range window | Dùng với time range phù hợp |

Một số lưu ý cơ bản:

1. `output` có thể định nghĩa **nhiều field tính toán** trong cùng một stage.
2. `$setWindowFields` thêm các field vào document đầu ra, không tự thay toàn bộ document.
3. Có thể dùng nhiều `$setWindowFields` stages trong pipeline nếu cần thứ tự khác nhau.
4. Nếu **bỏ `window`** ở operator hỗ trợ, mặc định thường là **unbounded window chứa toàn partition**, **không phải tổng lũy kế đến dòng hiện tại**.
5. Các rank operators như `$rank` và `$denseRank` dùng **implicit window**: **không khai báo `window`** cho chúng.
6. Stage này **không bảo đảm thứ tự document được trả ra**. Nếu API cần thứ tự cuối cùng, thêm `$sort` riêng sau stage.

### 2.1. Mô hình một partition

~~~text
Partition: HCM
sortBy: { day: 1, _id: 1 }

dòng 1     dòng 2     dòng 3     dòng 4
  100        200        200         50
   |----------|----------|----------|

Window tại dòng 3:
  documents: ["unbounded", "current"]
  => [100, 200, 200] => $sum = 500

Window tại dòng 3:
  documents: [-1, 0]
  => [200, 200] => $sum = 400

Window tại dòng 3:
  documents: ["unbounded", "unbounded"]
  => [100, 200, 200, 50] => $sum = 550
~~~

Trong mọi cửa sổ, hai biên là **inclusive** theo quy tắc `$setWindowFields`.

---

## 3. Chuẩn bị bộ dữ liệu mongosh có thể thực hành

Sử dụng database thử nghiệm, **không chạy các lệnh tạo/xóa trên production**.

~~~javascript
use window_analysis_lab

db.sales.insertMany([
  {
    _id: 1,
    store: "HCM",
    seller: "An",
    day: ISODate("2026-01-01T00:00:00Z"),
    revenue: 100
  },
  {
    _id: 2,
    store: "HCM",
    seller: "Bình",
    day: ISODate("2026-01-02T00:00:00Z"),
    revenue: 200
  },
  {
    _id: 3,
    store: "HCM",
    seller: "Chi",
    day: ISODate("2026-01-02T00:00:00Z"),
    revenue: 200
  },
  {
    _id: 4,
    store: "HCM",
    seller: "Dung",
    day: ISODate("2026-01-04T00:00:00Z"),
    revenue: 50
  },
  {
    _id: 5,
    store: "HN",
    seller: "Hà",
    day: ISODate("2026-01-01T00:00:00Z"),
    revenue: 150
  },
  {
    _id: 6,
    store: "HN",
    seller: "Lan",
    day: ISODate("2026-01-03T00:00:00Z"),
    revenue: 150
  },
  {
    _id: 7,
    store: "HN",
    seller: "Minh",
    day: ISODate("2026-01-04T00:00:00Z"),
    revenue: 300
  },
  {
    _id: 8,
    store: "DN",
    seller: "Ngọc",
    day: ISODate("2026-01-02T00:00:00Z"),
    revenue: 0
  },
  {
    _id: 9,
    store: "DN",
    seller: "Phúc",
    day: ISODate("2026-01-03T00:00:00Z"),
    revenue: null
  },
  {
    _id: 10,
    store: "DN",
    seller: "Quân",
    day: ISODate("2026-01-04T00:00:00Z")
  }
]);
~~~

Kiểm tra:

~~~javascript
db.sales.countDocuments({});

db.sales.find(
  {},
  { _id: 1, store: 1, seller: 1, day: 1, revenue: 1 }
).sort({ store: 1, day: 1, _id: 1 });
~~~

Nếu chỉ chạy insert một lần, tập lab có **10 document**.

Tính chất dữ liệu được tạo có chủ đích:

- **HCM:** 4 giao dịch, hai dòng cùng ngày 02/01, doanh thu 200 bị trùng.
- **HN:** 3 giao dịch, hai dòng doanh thu 150 bị trùng.
- **DN:** 3 giao dịch, một dòng revenue bằng 0, một bằng `null`, một **thiếu field revenue**.
- `_id` là duy nhất, thuận tiện để phân xử các dòng trùng timestamp khi cần thứ tự ổn định.
- Ngày là kiểu BSON Date, thích hợp với time-range window.

Khi muốn chạy lại lab, hãy dùng database/collection mới hoặc xóa dữ liệu lab theo kế hoạch. Không thực hiện các lệnh xóa rộng ngoài phạm vi thực hành.

---

## 4. Tổng lũy kế với `$sum` và `documents: ["unbounded", "current"]`

### 4.1. Câu hỏi nghiệp vụ

"Đến **mỗi giao dịch**, cửa hàng đã tích lũy bao nhiêu doanh thu?"

Với HCM, thứ tự theo ngày tăng dần và `_id` tăng dần:

| `_id` | Day | Revenue | Running total |
|---:|---|---:|---:|
| 1 | 01/01 | 100 | 100 |
| 2 | 02/01 | 200 | 300 |
| 3 | 02/01 | 200 | 500 |
| 4 | 04/01 | 50 | 550 |

Điểm then chốt: hai giao dịch cùng ngày được phân xử bằng `_id`, giúp kết quả tích lũy **theo từng dòng** có thứ tự xác định.

### 4.2. Pipeline

~~~javascript
db.sales.aggregate([
  {
    $setWindowFields: {
      partitionBy: "$store",
      sortBy: {
        day: 1,
        _id: 1
      },
      output: {
        runningRevenue: {
          $sum: "$revenue",
          window: {
            documents: [
              "unbounded",
              "current"
            ]
          }
        }
      }
    }
  },
  {
    $sort: {
      store: 1,
      day: 1,
      _id: 1
    }
  },
  {
    $project: {
      _id: 1,
      store: 1,
      seller: 1,
      day: 1,
      revenue: 1,
      runningRevenue: 1
    }
  }
]);
~~~

Giải thích:

- `partitionBy: "$store"` tạo ba partition HCM, HN và DN.
- `sortBy: {day:1,_id:1}` sắp thứ tự giao dịch **bên trong mỗi partition**.
- `documents: ["unbounded","current"]` tính từ đầu partition đến dòng đang xét.
- `$sum: "$revenue"` cộng những revenue thuộc cửa sổ.
- `$sort` sau stage định nghĩa thứ tự **kết quả cuối**, bởi `$setWindowFields` không tự cam kết thứ tự output.

### 4.3. Kết quả minh họa cho ba partition


| Store | `_id` | Revenue | Running total |
|---|---:|---:|---:|
| DN | 8 | 0 | 0 |
| DN | 9 | null | 0 |
| DN | 10 | Missing | 0 |
| HCM | 1 | 100 | 100 |
| HCM | 2 | 200 | 300 |
| HCM | 3 | 200 | 500 |
| HCM | 4 | 50 | 550 |
| HN | 5 | 150 | 150 |
| HN | 6 | 150 | 300 |
| HN | 7 | 300 | 600 |

`$sum` với window bỏ qua giá trị không phải numeric theo các quy tắc accumulator phù hợp; những trường hợp null/missing trong DN không đóng góp doanh thu. **Đừng hiểu 0 lũy kế là bằng chứng mọi dòng có dữ liệu doanh thu hợp lệ.** Nếu cần bảo đảm chất lượng dữ liệu, phải đếm riêng số dòng null/missing/sai kiểu.

### 4.4. Vì sao cần khóa phân xử `_id`?

Nếu chỉ dùng:

~~~javascript
sortBy: { day: 1 }
~~~

thì hai giao dịch HCM cùng 02/01 có giá trị sort bằng nhau. Nếu yêu cầu chỉ là tổng **theo ngày**, cả hai cùng ngày có thể được xem là một nhóm giá trị thời gian. Nhưng nếu cần running total **theo từng transaction**, thứ tự giữa chúng phải rõ.

Với cửa sổ theo vị trí dòng, nếu các sort keys trùng nhau và không có tie-breaker, một giao dịch có thể nhận total 300 ở lần chạy này nhưng 500 ở lần khác trong một số điều kiện; không thiết kế ứng dụng dựa vào thứ tự không được bảo đảm.

Một lựa chọn phổ biến:

~~~javascript
sortBy: {
  day: 1,
  _id: 1
}
~~~

Tuy nhiên, nếu `_id` không phản ánh thứ tự nghiệp vụ thật, cần dùng một trường thứ tự khác như `sequenceNo`, `eventId` hoặc `ingestedAt + stable ID` đã được định nghĩa rõ.

---

## 5. Lưu ý đặc biệt: bỏ `window` không có nghĩa tổng lũy kế

So sánh hai output:

~~~javascript
db.sales.aggregate([
  {
    $setWindowFields: {
      partitionBy: "$store",
      sortBy: { day: 1, _id: 1 },
      output: {
        runningRevenue: {
          $sum: "$revenue",
          window: {
            documents: ["unbounded", "current"]
          }
        },
        storeRevenue: {
          $sum: "$revenue",
          window: {
            documents: ["unbounded", "unbounded"]
          }
        }
      }
    }
  },
  {
    $sort: { store: 1, day: 1, _id: 1 }
  }
]);
~~~

Ý nghĩa:

- `runningRevenue`: thay đổi từ dòng này sang dòng khác.
- `storeRevenue`: **tổng toàn partition**, giống nhau trên mọi dòng của cửa hàng.

Đối với HCM:

| ID | Running | Total store |
|---:|---:|---:|
| 1 | 100 | 550 |
| 2 | 300 | 550 |
| 3 | 500 | 550 |
| 4 | 550 | 550 |

Với các window operator hỗ trợ explicit window, nếu bỏ thuộc tính `window`, mặc định là **full partition**, không phải `["unbounded","current"]`.

Ví dụ:

~~~javascript
output: {
  storeRevenue: {
    $sum: "$revenue"
  }
}
~~~

là ý tưởng tính tổng toàn partition, **không** tạo chạy lũy kế theo dòng. Vì vậy, với running total, hãy luôn viết biên cửa sổ tường minh để tránh nhầm lẫn.

### 5.1. Khác biệt giữa cumulative và partition total

| Yêu cầu | Window | HCM dòng đầu |
|---|---|---:|
| Tổng lũy kế đến dòng | `documents:["unbounded","current"]` | 100 |
| Tổng toàn nhóm | `documents:["unbounded","unbounded"]` | 550 |
| Chỉ dòng hiện tại | `documents:["current","current"]` | 100 |
| Dòng hiện tại và dòng trước | `documents:[-1,0]` | 100 ở dòng đầu |
| 3 dòng gần nhất tính cả dòng hiện tại | `documents:[-2,0]` | 100 ở dòng đầu |

Các biên tương đối được **giới hạn bởi ranh giới partition**: window không tràn sang cửa hàng khác.

---

## 6. Tính nhiều chỉ số trong một `$setWindowFields`

Một báo cáo thực tế thường cần thêm các chỉ số khác cùng partition và sort.

~~~javascript
db.sales.aggregate([
  {
    $setWindowFields: {
      partitionBy: "$store",
      sortBy: { day: 1, _id: 1 },
      output: {
        runningRevenue: {
          $sum: "$revenue",
          window: {
            documents: ["unbounded", "current"]
          }
        },
        runningTransactions: {
          $count: {},
          window: {
            documents: ["unbounded", "current"]
          }
        },
        storeRevenue: {
          $sum: "$revenue",
          window: {
            documents: ["unbounded", "unbounded"]
          }
        },
        latestThreeAverage: {
          $avg: "$revenue",
          window: {
            documents: [-2, 0]
          }
        }
      }
    }
  },
  {
    $sort: { store: 1, day: 1, _id: 1 }
  }
]);
~~~

Các output:

| Field | Ý nghĩa |
|---|---|
| `runningRevenue` | Doanh thu từ đầu partition đến dòng hiện tại |
| `runningTransactions` | Số document từ đầu partition đến dòng hiện tại |
| `storeRevenue` | Tổng doanh thu toàn partition |
| `latestThreeAverage` | Trung bình revenue số của tối đa 3 dòng: 2 dòng trước và hiện tại |

### 6.1. Vì sao `runningTransactions` khác đếm doanh thu hợp lệ?

`$count` window đếm **document nằm trong cửa sổ**, kể cả document có revenue null hoặc thiếu revenue. Với DN:

| Dòng | Revenue | Running transactions | Running revenue |
|---:|---:|---:|---:|
| 8 | 0 | 1 | 0 |
| 9 | null | 2 | 0 |
| 10 | Missing | 3 | 0 |

Đó là điều mong đợi: ba giao dịch khác với ba giao dịch có **doanh thu numeric hợp lệ**.

Nếu muốn đếm doanh thu numeric, có thể dùng `$sum` trên biểu thức điều kiện:

~~~javascript
validRevenueCount: {
  $sum: {
    $cond: [
      { $isNumber: "$revenue" },
      1,
      0
    ]
  },
  window: {
    documents: ["unbounded", "current"]
  }
}
~~~

`$isNumber` là biểu thức aggregation. Nhờ vậy DN có validRevenueCount = 1 sau dòng 8, không tăng ở hai dòng null/missing.

### 6.2. Trung bình của ba giao dịch gần nhất

Cho HCM theo `day,_id`:

| ID | Doanh thu | Window 3 dòng | Average |
|---:|---:|---|---:|
| 1 | 100 | [100] | 100 |
| 2 | 200 | [100,200] | 150 |
| 3 | 200 | [100,200,200] | ≈166,67 |
| 4 | 50 | [200,200,50] | 150 |

Nếu cửa sổ chứa null/missing hoặc string không phải number, `$avg` bỏ qua các giá trị không phải numeric theo accumulator semantics; khi không có số hợp lệ, kết quả có thể là null.

**Không** dùng trung bình này như doanh thu trung bình theo **ba ngày**: nó tính theo ba **document**, trong khi HCM có hai giao dịch cùng ngày.

---

## 7. Xếp hạng với `$rank`, `$denseRank` và `$documentNumber`

Ba operator thường gây nhầm lẫn nhất khi làm leaderboard:

| Operator | Có gộp những giá trị bằng nhau thành cùng hạng? | Có bỏ số hạng sau tie? |
|---|---|---|
| `$rank` | **Có** | **Có** |
| `$denseRank` | **Có** | **Không** |
| `$documentNumber` | **Không**; mỗi document có một số riêng | Không theo ý nghĩa xếp hạng cùng hạng |

Giả sử thứ tự điểm giảm dần: 90, 80, 80, 70.

| Điểm | `$rank` | `$denseRank` | `$documentNumber` |
|---:|---:|---:|---:|
| 90 | 1 | 1 | 1 |
| 80 | 2 | 2 | 2 |
| 80 | 2 | 2 | 3 |
| 70 | 4 | 3 | 4 |

**Khái niệm:**

- **Competition rank (`$rank`):** hai người bằng điểm chiếm hai vị trí, người sau nhảy hạng.
- **Dense rank (`$denseRank`):** các mức điểm khác nhau có thứ hạng liên tiếp, không có khoảng trống.
- **Row number (`$documentNumber`):** số thứ tự duy nhất theo sort trong partition; nếu các sort key trùng nhau, phải có cách phân xử để kết quả ổn định.

### 7.1. Cú pháp

~~~javascript
{
  $setWindowFields: {
    partitionBy: "$store",
    sortBy: {
      revenue: -1
    },
    output: {
      competitionRank: {
        $rank: {}
      },
      denseRank: {
        $denseRank: {}
      }
    }
  }
}
~~~

Điểm quan trọng:

1. `$rank` và `$denseRank` được sử dụng **trong `$setWindowFields`**.
2. Cú pháp từng operator là object rỗng: `{$rank:{}}` và `{$denseRank:{}}`.
3. Chúng **không nhận `window`** vì dùng implicit window.
4. `sortBy` cần có để xác định thứ hạng.
5. Với **`$rank`** và **`$denseRank`**, `sortBy` cho phép **một field** làm khóa xếp hạng theo yêu cầu của operator; không dùng thêm `_id` trong cùng `sortBy` nếu vẫn muốn xếp hạng bằng đúng một metric.

### 7.2. Tại sao không dùng `sortBy:{revenue:-1,_id:1}` cho `$rank`?

Mục đích của `$rank` là cho những document có cùng revenue **cùng hạng**. Nếu thêm `_id` làm khóa phụ vào tiêu chí đánh hạng, những dòng revenue bằng nhau có thể bị phân biệt thành tổ hợp sort key khác nhau; đồng thời, `$rank` còn có ràng buộc **một field sortBy**.

Cách đúng:

- **Dùng `sortBy:{revenue:-1}` để tính rank/tie**.
- **Dùng `$sort:{store:1,revenue:-1,_id:1}` sau stage** để hiển thị ổn định.
- Nếu yêu cầu "chỉ lấy đúng 3 dòng" thay vì "các dòng nằm trong 3 hạng", dùng `$documentNumber` trong một stage khác với sort có khóa phân xử phù hợp.

---

## 8. Bảng xếp hạng thực hành trên doanh thu

### 8.1. Loại null/missing trước khi xếp hạng số

Bộ dữ liệu DN có null/missing revenue. Nếu yêu cầu leaderboard cho doanh thu hợp lệ, nên lọc:

~~~javascript
db.sales.aggregate([
  {
    $match: {
      revenue: {
        $type: "number"
      }
    }
  },
  {
    $setWindowFields: {
      partitionBy: "$store",
      sortBy: {
        revenue: -1
      },
      output: {
        competitionRank: {
          $rank: {}
        },
        denseRank: {
          $denseRank: {}
        }
      }
    }
  },
  {
    $sort: {
      store: 1,
      revenue: -1,
      _id: 1
    }
  },
  {
    $project: {
      _id: 1,
      store: 1,
      seller: 1,
      revenue: 1,
      competitionRank: 1,
      denseRank: 1
    }
  }
]);
~~~

`$type:"number"` trong query lọc các kiểu BSON numeric phù hợp. Nếu doanh thu bị lưu dưới dạng string numeric, query này không tự convert chúng; cần làm sạch dữ liệu hoặc chính sách conversion riêng.

### 8.2. Dự kiến cho HCM

Trong HCM: revenue giảm dần là 200, 200, 100, 50.

| Seller | Revenue | `$rank` | `$denseRank` |
|---|---:|---:|---:|
| Bình | 200 | 1 | 1 |
| Chi | 200 | 1 | 1 |
| An | 100 | 3 | 2 |
| Dung | 50 | 4 | 3 |

Hai người Bình và Chi cùng rank 1. Với `$rank`, hạng 2 **bị bỏ qua** và An nhận hạng 3. Với `$denseRank`, An nhận hạng 2.

### 8.3. Dự kiến cho HN

Dữ liệu HN: 300, 150, 150.

| Seller | Revenue | `$rank` | `$denseRank` |
|---|---:|---:|---:|
| Minh | 300 | 1 | 1 |
| Hà | 150 | 2 | 2 |
| Lan | 150 | 2 | 2 |

### 8.4. Lưu ý về semantics của từng dòng

Trong bộ lab, mỗi giao dịch gắn với một seller. Nếu một seller có **nhiều giao dịch**, pipeline trên xếp hạng **giao dịch**, không xếp hạng **tổng doanh thu của seller**.

Muốn leaderboard **seller theo doanh thu tháng**, phải `$group` theo seller trước, sau đó `$setWindowFields` để rank các document tổng hợp. Đây là khác biệt rất quan trọng trong nghiệp vụ.

---

## 9. Xếp hạng doanh thu theo nhân viên sau `$group`

### 9.1. Bài toán

Mỗi seller có thể có nhiều giao dịch. Muốn lấy bảng xếp hạng **tổng revenue theo seller** trong từng cửa hàng.

Pipeline:

~~~javascript
db.sales.aggregate([
  {
    $match: {
      revenue: { $type: "number" }
    }
  },
  {
    $group: {
      _id: {
        store: "$store",
        seller: "$seller"
      },
      sellerRevenue: {
        $sum: "$revenue"
      },
      transactionCount: {
        $sum: 1
      }
    }
  },
  {
    $set: {
      store: "$_id.store",
      seller: "$_id.seller"
    }
  },
  {
    $setWindowFields: {
      partitionBy: "$store",
      sortBy: {
        sellerRevenue: -1
      },
      output: {
        rankInStore: {
          $rank: {}
        },
        denseRankInStore: {
          $denseRank: {}
        }
      }
    }
  },
  {
    $sort: {
      store: 1,
      rankInStore: 1,
      seller: 1
    }
  },
  {
    $project: {
      _id: 0,
      store: 1,
      seller: 1,
      sellerRevenue: 1,
      transactionCount: 1,
      rankInStore: 1,
      denseRankInStore: 1
    }
  }
]);
~~~

Ở bộ lab này mỗi seller chỉ có một giao dịch. Nhưng cách viết vẫn đúng về **đơn vị xếp hạng** nếu dữ liệu thực có nhiều giao dịch mỗi seller.

### 9.2. Vì sao `$group` đặt trước?

Thứ tự:

~~~text
sales transactions
       |
       v
$group by (store,seller)
       |
       v
mỗi seller = một document doanh thu tổng
       |
       v
$setWindowFields rank theo sellerRevenue
       |
       v
một dòng = một seller với thứ hạng trong store
~~~

Nếu đặt rank trước group, kết quả rank theo **từng transaction**, không phải theo người bán. Có thể dẫn đến xếp hạng sai dù cú pháp chạy hoàn toàn hợp lệ.

### 9.3. Phân vùng theo nhiều thuộc tính

Khi có nhiều tháng và cửa hàng, có thể xây field phân vùng:

~~~javascript
db.sales.aggregate([
  {
    $set: {
      saleMonth: {
        $dateTrunc: {
          date: "$day",
          unit: "month",
          timezone: "Asia/Ho_Chi_Minh"
        }
      }
    }
  },
  {
    $match: {
      revenue: {
        $type: "number"
      }
    }
  },
  {
    $group: {
      _id: {
        store: "$store",
        saleMonth: "$saleMonth",
        seller: "$seller"
      },
      sellerRevenue: {
        $sum: "$revenue"
      }
    }
  },
  {
    $setWindowFields: {
      partitionBy: {
        store: "$_id.store",
        saleMonth: "$_id.saleMonth"
      },
      sortBy: {
        sellerRevenue: -1
      },
      output: {
        monthlyRank: {
          $denseRank: {}
        }
      }
    }
  },
  {
    $sort: {
      "_id.store": 1,
      "_id.saleMonth": 1,
      monthlyRank: 1,
      "_id.seller": 1
    }
  }
]);
~~~

`partitionBy` ở đây là một **biểu thức tạo khóa nhóm**, không chỉ nhất thiết một string field path. Các cửa hàng và tháng được tách riêng. `$dateTrunc` và tên timezone giúp tháng theo lịch nghiệp vụ được xác định rõ khi thời gian lưu dưới dạng UTC.

---

## 10. `$documentNumber`: số thứ tự duy nhất, có khóa phân xử

### 10.1. Phân biệt "cùng hạng" với "mỗi dòng có số riêng"

Nếu hai seller bằng doanh thu 200:

- `$rank`: cả hai có rank 1.
- `$denseRank`: cả hai có dense rank 1.
- `$documentNumber`: phải có số thứ tự khác nhau, ví dụ 1 và 2.

Để bảo đảm thứ tự xác định trong trường hợp cùng doanh thu, dùng một khóa phụ duy nhất trong `sortBy` cho phép với `$documentNumber`:

~~~javascript
db.sales.aggregate([
  {
    $match: {
      revenue: {
        $type: "number"
      }
    }
  },
  {
    $setWindowFields: {
      partitionBy: "$store",
      sortBy: {
        revenue: -1,
        _id: 1
      },
      output: {
        rowNumber: {
          $documentNumber: {}
        }
      }
    }
  },
  {
    $sort: {
      store: 1,
      rowNumber: 1
    }
  }
]);
~~~

Với HCM, theo `revenue DESC, _id ASC`:

| ID | Revenue | Row number |
|---:|---:|---:|
| 2 | 200 | 1 |
| 3 | 200 | 2 |
| 1 | 100 | 3 |
| 4 | 50 | 4 |

### 10.2. Khi nào dùng rank và khi nào dùng row number?

| Yêu cầu | Chọn |
|---|---|
| Huy chương: nhiều người đồng giải nhất | `$rank` |
| Các nhóm điểm từ cao xuống thấp không bỏ hạng | `$denseRank` |
| Phân trang hoặc lấy đúng N document theo tiêu chí | `$documentNumber` với sort ổn định |
| "Top 3 hạng" có thể bao gồm hơn 3 document | `$rank`/`$denseRank` tùy quy tắc |
| "Đúng 3 dòng đầu" bất kể đồng điểm | `$documentNumber` |
| Bảng leaderboard xếp đồng hạng nhưng muốn hiển thị ổn định | `$rank`/`$denseRank` rồi `$sort` thêm khóa phụ |

### 10.3. Không thay `$rank` bằng `$documentNumber` khi có tie

Một leaderboard ghi rank 1, 2, 3 cho hai người bằng điểm có thể trái quy tắc giải thưởng. Dùng document number chỉ khi sản phẩm thật sự muốn **số thứ tự dòng**, không muốn đồng hạng.

---

## 11. Lấy Top N: có giữ đồng hạng hay không?

### 11.1. Top 2 hạng với `$rank`

~~~javascript
db.sales.aggregate([
  {
    $match: {
      revenue: {
        $type: "number"
      }
    }
  },
  {
    $setWindowFields: {
      partitionBy: "$store",
      sortBy: {
        revenue: -1
      },
      output: {
        rankInStore: {
          $rank: {}
        }
      }
    }
  },
  {
    $match: {
      rankInStore: {
        $lte: 2
      }
    }
  },
  {
    $sort: {
      store: 1,
      rankInStore: 1,
      revenue: -1,
      _id: 1
    }
  }
]);
~~~

Với HCM, hai dòng revenue 200 đều có rank 1 nên cùng được trả. Dòng revenue 100 có rank 3, không thuộc Top 2 theo competition rank.

Với HN, Minh rank 1 và Hà/Lan cùng rank 2: truy vấn Top 2 **trả 3 document** ở HN. Đây là kết quả đúng nếu Top 2 **hạng**, chứ không phải "đúng hai dòng".

### 11.2. Top 2 mức điểm với `$denseRank`

~~~javascript
db.sales.aggregate([
  {
    $match: {
      revenue: {
        $type: "number"
      }
    }
  },
  {
    $setWindowFields: {
      partitionBy: "$store",
      sortBy: {
        revenue: -1
      },
      output: {
        denseRankInStore: {
          $denseRank: {}
        }
      }
    }
  },
  {
    $match: {
      denseRankInStore: {
        $lte: 2
      }
    }
  },
  {
    $sort: {
      store: 1,
      denseRankInStore: 1,
      _id: 1
    }
  }
]);
~~~

Với HCM, Top 2 **mức revenue** bao gồm 200, 200 và 100, tức 3 dòng.

### 11.3. Đúng 2 document với `$documentNumber`

~~~javascript
db.sales.aggregate([
  {
    $match: {
      revenue: {
        $type: "number"
      }
    }
  },
  {
    $setWindowFields: {
      partitionBy: "$store",
      sortBy: {
        revenue: -1,
        _id: 1
      },
      output: {
        rowNumber: {
          $documentNumber: {}
        }
      }
    }
  },
  {
    $match: {
      rowNumber: {
        $lte: 2
      }
    }
  },
  {
    $sort: {
      store: 1,
      rowNumber: 1
    }
  }
]);
~~~

Cách này chọn tối đa hai document mỗi store. Nếu chỉ có một document hợp lệ trong DN, kết quả DN có một dòng; không tự tạo dòng thứ hai.

**Bài toán product phải định nghĩa rõ:** "Top 2 hạng" và "Top 2 dòng" là hai yêu cầu khác nhau.

---

## 12. Cửa sổ theo document: moving sum và moving average

### 12.1. Ba giao dịch gần nhất

~~~javascript
db.sales.aggregate([
  {
    $setWindowFields: {
      partitionBy: "$store",
      sortBy: {
        day: 1,
        _id: 1
      },
      output: {
        last3Revenue: {
          $sum: "$revenue",
          window: {
            documents: [-2, 0]
          }
        },
        last3Average: {
          $avg: "$revenue",
          window: {
            documents: [-2, 0]
          }
        }
      }
    }
  },
  {
    $sort: {
      store: 1,
      day: 1,
      _id: 1
    }
  }
]);
~~~

`[-2,0]` nghĩa là **hai document trước + document hiện tại**; tất cả đều nằm trong partition của store.

Với HCM:

| ID | Revenue | Last 3 revenue | Last 3 avg |
|---:|---:|---:|---:|
| 1 | 100 | 100 | 100 |
| 2 | 200 | 300 | 150 |
| 3 | 200 | 500 | ≈166,67 |
| 4 | 50 | 450 | 150 |

### 12.2. Ranh giới partition

Tại dòng đầu của HN, dù ngay trước đó trong thứ tự hiển thị có thể là giao dịch HCM, cửa sổ không lấy doanh thu HCM. Nó **dừng ở đầu partition HN**.

Điều này khác một moving average trên toàn collection. Nếu bỏ `partitionBy`, toàn bộ input trở thành một partition và cửa sổ có thể trộn các cửa hàng.

### 12.3. Thay đổi độ rộng cửa sổ

Các ví dụ hợp lệ khi operator hỗ trợ bounded documents window:

~~~javascript
// Chỉ dòng hiện tại.
documents: ["current", "current"]

// Dòng trước và hiện tại.
documents: [-1, 0]

// Hai dòng trước và hai dòng sau, có cả hiện tại.
documents: [-2, 2]

// Từ đầu nhóm đến dòng hiện tại.
documents: ["unbounded", "current"]

// Từ hiện tại đến cuối nhóm.
documents: ["current", "unbounded"]

// Toàn partition.
documents: ["unbounded", "unbounded"]
~~~

Các giá trị số trong `documents` là **độ lệch theo vị trí dòng**, không phải số ngày, giây hoặc giá trị revenue.

---

## 13. Cửa sổ theo khoảng giá trị: `range`

### 13.1. Phân biệt "ba dòng" với "ba đơn vị giá trị"

`documents:[-2,0]` dùng **hai dòng trước**. `range:[-2,0]` dùng **giá trị của sortBy field nằm trong khoảng từ giá trị hiện tại trừ 2 đến hiện tại**, theo ngữ nghĩa range window.

Ví dụ collection `measurements`:

~~~javascript
db.measurements.insertMany([
  { _id: 1, sensor: "S1", minute: 1, value: 10 },
  { _id: 2, sensor: "S1", minute: 2, value: 20 },
  { _id: 3, sensor: "S1", minute: 2, value: 30 },
  { _id: 4, sensor: "S1", minute: 5, value: 40 }
]);
~~~

Cửa sổ theo giá trị `minute`:

~~~javascript
db.measurements.aggregate([
  {
    $setWindowFields: {
      partitionBy: "$sensor",
      sortBy: {
        minute: 1
      },
      output: {
        nearValueSum: {
          $sum: "$value",
          window: {
            range: [-2, 0]
          }
        }
      }
    }
  },
  {
    $sort: {
      sensor: 1,
      minute: 1,
      _id: 1
    }
  }
]);
~~~

Ở minute 2, range [-2,0] lấy những dòng có minute từ 0 đến 2, gồm minute 1 và **cả hai dòng minute 2**, nên tổng là 10+20+30=60. Ở minute 5, lấy minute trong [3,5], nên chỉ có dòng 40.

Đây là khác biệt quan trọng với cửa sổ theo số document: các bản ghi **trùng giá trị sortBy** cùng thuộc một khoảng giá trị, trong khi một documents window theo thứ tự dòng có thể dừng ở giữa các bản ghi cùng giá trị.

### 13.2. Quy tắc quan trọng của `range`

- Một range window dùng **một trường trong `sortBy`**, theo **chiều tăng dần**.
- Với numeric range, giá trị sortBy phù hợp phải là **number**.
- Range boundaries tính theo **giá trị sortBy** và **bao gồm hai đầu**.
- `null`, missing và các giá trị không tương thích không được đưa vào numeric range theo quy tắc window.
- Không khai báo đồng thời `documents` và `range` trong cùng một `window`.

Không dùng:

~~~javascript
// Không phải thiết kế range window hợp lệ:
{
  sortBy: {
    minute: 1,
    _id: 1
  },
  output: {
    moving: {
      $sum: "$value",
      window: {
        range: [-2, 0]
      }
    }
  }
}
~~~

vì range window chỉ dùng một sortBy field. Nếu cần tie-breaker từng dòng và thứ tự ổn định theo vị trí, hãy cân nhắc **documents window** thay vì range.

---

## 14. Time range window: doanh thu theo hai ngày gần nhất

### 14.1. Bài toán

Muốn với mỗi dòng giao dịch, tính doanh thu những bản ghi có timestamp **trong hai ngày trước đến thời điểm của dòng hiện tại**, không phải chỉ lấy hai transaction trước đó.

Dùng time range window:

~~~javascript
db.sales.aggregate([
  {
    $setWindowFields: {
      partitionBy: "$store",
      sortBy: {
        day: 1
      },
      output: {
        revenueWithinTwoDays: {
          $sum: "$revenue",
          window: {
            range: [-2, "current"],
            unit: "day"
          }
        }
      }
    }
  },
  {
    $sort: {
      store: 1,
      day: 1,
      _id: 1
    }
  }
]);
~~~

Các yêu cầu:

- `sortBy` có **một field** và chiều **tăng dần**.
- Field sortBy là kiểu date/time phù hợp.
- `unit: "day"` khai báo khoảng thời gian.
- Biên `[-2, "current"]` lấy từ hai ngày trước đến timestamp của dòng hiện tại, hai đầu inclusive.
- Giá trị biên thời gian tính bằng đơn vị nguyên hợp lệ; không tự dùng `-1.5` ngày rồi kỳ vọng được chấp nhận.

### 14.2. Phân tích HCM

Dữ liệu HCM:

| ID | Ngày | Revenue |
|---:|---|---:|
| 1 | 01/01 | 100 |
| 2 | 02/01 | 200 |
| 3 | 02/01 | 200 |
| 4 | 04/01 | 50 |

- Dòng 1 (01/01): khoảng 30/12–01/01 → chỉ 100.
- Hai dòng 2 và 3 (02/01): khoảng 31/12–02/01 → 100+200+200 = **500** cho **cả hai dòng có timestamp bằng nhau**.
- Dòng 4 (04/01): khoảng 02/01–04/01 → 200+200+50 = **450**.

So với running total theo documents:

| ID | Running total theo thứ tự từng dòng | Two-day time range total |
|---:|---:|---:|
| 1 | 100 | 100 |
| 2 | 300 | 500 |
| 3 | 500 | 500 |
| 4 | 550 | 450 |

Một kết quả có thể khác nhau **mặc dù đều tính `$sum`**, vì định nghĩa window khác nhau.

### 14.3. Vì sao time range không thể dùng hai khóa sort?

Cửa sổ thời gian được xác định từ **một giá trị ngày/giờ**. Nếu đồng thời sort theo `day` và `_id`, server không có một phạm vi đơn giản "hai ngày trước" trên tổ hợp hai field. Vì vậy, khi cần time range:

~~~javascript
sortBy: {
  day: 1
}
~~~

Và nếu cần thứ tự hiển thị ổn định, thêm `$sort` sau `$setWindowFields`:

~~~javascript
{
  $sort: {
    store: 1,
    day: 1,
    _id: 1
  }
}
~~~

### 14.4. Documents và time range không thể thay thế hoàn toàn

| Mong muốn | Nên dùng |
|---|---|
| Doanh thu của 5 transaction gần nhất | `documents:[-4,0]` |
| Doanh thu trong 7 ngày gần nhất | `range:[-7,"current"],unit:"day"` |
| Tổng lũy kế của tất cả transaction trước dòng hiện tại | `documents:["unbounded","current"]` |
| Tổng toàn partition | Full partition window |
| Xếp hạng theo score/revenue | Rank operator, không khai báo window |
| Lấy đúng 10 dòng gần nhất | `$documentNumber` với sort ổn định rồi lọc |

---

## 15. Tính tỷ trọng và tỷ lệ hoàn thành nhờ hai cửa sổ

### 15.1. Câu hỏi

"Đến giao dịch hiện tại, cửa hàng đã đạt bao nhiêu **phần trăm tổng doanh thu của cả kỳ**?"

Cần:

1. `runningRevenue` từ đầu đến dòng.
2. `storeRevenue` của toàn partition.
3. `$divide` và `$multiply` để tính percentage.
4. Xử lý mẫu số bằng 0.

### 15.2. Pipeline

~~~javascript
db.sales.aggregate([
  {
    $setWindowFields: {
      partitionBy: "$store",
      sortBy: {
        day: 1,
        _id: 1
      },
      output: {
        runningRevenue: {
          $sum: "$revenue",
          window: {
            documents: ["unbounded", "current"]
          }
        },
        storeRevenue: {
          $sum: "$revenue",
          window: {
            documents: ["unbounded", "unbounded"]
          }
        }
      }
    }
  },
  {
    $set: {
      runningSharePercent: {
        $cond: {
          if: {
            $gt: ["$storeRevenue", 0]
          },
          then: {
            $multiply: [
              {
                $divide: [
                  "$runningRevenue",
                  "$storeRevenue"
                ]
              },
              100
            ]
          },
          else: null
        }
      }
    }
  },
  {
    $sort: {
      store: 1,
      day: 1,
      _id: 1
    }
  },
  {
    $project: {
      _id: 1,
      store: 1,
      seller: 1,
      runningRevenue: 1,
      storeRevenue: 1,
      runningSharePercent: 1
    }
  }
]);
~~~

HCM có total 550, nên tỷ lệ tại các dòng khoảng 18,18%, 54,55%, 90,91% và 100%. HN có tổng 600. DN có tổng 0 và trả `null` cho phần trăm theo chính sách trong `$cond`, thay vì phép chia cho 0 gây lỗi.

### 15.3. Tỷ trọng doanh thu của một dòng khác tỷ trọng lũy kế

Nếu muốn "giao dịch hiện tại chiếm bao nhiêu % tổng cửa hàng":

~~~javascript
{
  $divide: [
    "$revenue",
    "$storeRevenue"
  ]
}
~~~

sau khi kiểm tra revenue numeric và storeRevenue khác 0.

Còn `runningRevenue/storeRevenue` cho tỷ trọng **tích lũy**. Hai metric khác nhau; tên field nên phản ánh rõ.

### 15.4. Không tự giả định tổng luôn không âm

Ví dụ doanh thu có hoàn tiền hoặc negative corrections, tổng toàn partition có thể bằng 0 hoặc âm. Điều kiện `$gt: ["$storeRevenue",0]` ở trên là **quyết định nghiệp vụ của ví dụ**. Trong hệ thống thực, phải xác định cách xử lý refund, net revenue và mẫu số âm.

---

## 16. Trùng timestamp, trùng điểm và tính ổn định của kết quả

### 16.1. Với running total: quan trọng thứ tự dòng

Hai đơn cùng timestamp nhưng revenue khác nhau:

~~~javascript
{ _id: 100, day: ISODate("2026-01-02T00:00:00Z"), revenue: 10 }
{ _id: 101, day: ISODate("2026-01-02T00:00:00Z"), revenue: 20 }
~~~

Nếu cửa sổ theo `documents:["unbounded","current"]`, dòng nào đứng trước quyết định ai nhận running 10 và ai nhận running 30. Khi chỉ sortBy `day`, thứ tự tie không được định nghĩa đầy đủ.

Giải pháp khi bài toán cần từng dòng ổn định:

~~~javascript
sortBy: {
  day: 1,
  _id: 1
}
~~~

Nếu cần chuẩn sự kiện theo thời gian nghiệp vụ, có thể dùng sequence number từ nguồn; `_id` chỉ là tie-breaker ổn định, không tự đảm bảo là thời gian giao dịch thật.

### 16.2. Với rank: tie phải được giữ

Ngược lại, khi rank theo revenue, hai người có cùng revenue cần cùng hạng. Không thêm `_id` vào tiêu chí đánh rank nếu điều đó thay đổi khái niệm đồng hạng, và `$rank`/`$denseRank` có giới hạn một sortBy field.

Tách rõ:

~~~text
Xếp hạng:
  sortBy revenue DESC
  => những revenue bằng nhau cùng rank

Hiển thị:
  $sort store ASC, rank ASC, _id ASC
  => dòng có cùng rank hiển thị ổn định
~~~

### 16.3. Với `$documentNumber`: tie-breaker có ý nghĩa

`$documentNumber` cho số thứ tự duy nhất trên từng dòng trong partition, nhưng nếu các sort keys không unique, chính xác document nào nhận số 1/2 khi giá trị bằng nhau có thể không ổn định. Dùng `sortBy:{revenue:-1,_id:1}` khi cần xác định một cách nhất quán.

### 16.4. Stage `$setWindowFields` không bảo đảm output order

Đây là lỗi dễ bỏ sót:

~~~javascript
db.sales.aggregate([
  {
    $setWindowFields: {
      partitionBy: "$store",
      sortBy: { day: 1, _id: 1 },
      output: {
        runningRevenue: {
          $sum: "$revenue",
          window: {
            documents: ["unbounded", "current"]
          }
        }
      }
    }
  }
]);
~~~

Dù có `sortBy` ở trong stage, kết quả cuối **không được bảo đảm trả theo thứ tự đó**. Nếu frontend hoặc báo cáo cần thứ tự, thêm:

~~~javascript
{
  $sort: {
    store: 1,
    day: 1,
    _id: 1
  }
}
~~~

Không dựa vào thứ tự ngẫu nhiên của output để kiểm thử hay phân trang.

---

## 17. Missing/null và kiểu BSON trong tính lũy kế, xếp hạng

### 17.1. `$sum` không làm dữ liệu null thành "doanh thu hợp lệ"

Với DN:

~~~javascript
{ _id: 8, revenue: 0 }
{ _id: 9, revenue: null }
{ _id: 10 }
~~~

Tổng lũy kế là 0, 0, 0. Nhưng ý nghĩa của ba dòng khác nhau:

- ID 8 có số 0 hợp lệ.
- ID 9 có field revenue = null.
- ID 10 thiếu revenue.

Nếu báo cáo cần biết mức độ đầy đủ dữ liệu, thêm một chỉ số:

~~~javascript
db.sales.aggregate([
  {
    $set: {
      revenueState: {
        $switch: {
          branches: [
            {
              case: {
                $eq: [
                  { $type: "$revenue" },
                  "missing"
                ]
              },
              then: "MISSING"
            },
            {
              case: {
                $eq: [
                  { $type: "$revenue" },
                  "null"
                ]
              },
              then: "NULL"
            },
            {
              case: {
                $isNumber: "$revenue"
              },
              then: "VALID"
            }
          ],
          default: "INVALID_TYPE"
        }
      }
    }
  },
  {
    $setWindowFields: {
      partitionBy: "$store",
      sortBy: { day: 1, _id: 1 },
      output: {
        runningRevenue: {
          $sum: "$revenue",
          window: {
            documents: ["unbounded", "current"]
          }
        },
        invalidCount: {
          $sum: {
            $cond: [
              { $eq: ["$revenueState", "VALID"] },
              0,
              1
            ]
          },
          window: {
            documents: ["unbounded", "current"]
          }
        }
      }
    }
  },
  {
    $sort: { store: 1, day: 1, _id: 1 }
  }
]);
~~~

DN nhận `invalidCount` = 0,1,2 theo các dòng. Như vậy không còn nhầm tổng 0 với dữ liệu đầu vào hoàn toàn hợp lệ.

### 17.2. Ranking có field null hoặc missing

`$rank` và `$denseRank` sử dụng thứ tự so sánh BSON để đặt document có sort field null/missing vào thứ tự tương ứng. **Kể từ MongoDB 8.0, null và missing trong phép xếp hạng bằng các toán tử này được coi tương đương**; phiên bản cũ có khác biệt liên quan cần kiểm tra khi nâng cấp.

Nếu nghiệp vụ không muốn các record null/missing tham gia leaderboard, **lọc trước rank**:

~~~javascript
{
  $match: {
    revenue: {
      $type: "number"
    }
  }
}
~~~

Đừng gán ý nghĩa "hạng cuối" cho dữ liệu lỗi một cách ngầm định. Một bảng xếp hạng nhân viên có revenue chưa xác định thường nên báo "chưa đủ dữ liệu" riêng.

### 17.3. String-number không phải number

Ví dụ:

~~~javascript
{
  revenue: "200"
}
~~~

`$sum` không tự coi string đó là số 200 theo cách kế toán yêu cầu. Với rank, trộn numeric và string sẽ dùng BSON comparison order thay vì so sánh numeric thuần.

Nếu dữ liệu lịch sử có string numbers, cân nhắc chuẩn hóa trong pipeline:

~~~javascript
db.sales.aggregate([
  {
    $set: {
      revenueNumber: {
        $convert: {
          input: "$revenue",
          to: "decimal",
          onError: null,
          onNull: null
        }
      }
    }
  },
  {
    $setWindowFields: {
      partitionBy: "$store",
      sortBy: { day: 1, _id: 1 },
      output: {
        runningRevenue: {
          $sum: "$revenueNumber",
          window: {
            documents: ["unbounded", "current"]
          }
        }
      }
    }
  }
]);
~~~

`$convert` với `onError` và `onNull` bảo vệ pipeline khỏi parse error thông thường, nhưng việc gộp parse error và null thành một trạng thái có thể **che giấu lỗi dữ liệu**. Với báo cáo tài chính, nên giữ thêm field trạng thái conversion hoặc validation từ nguồn.

### 17.4. Tránh kiểu numeric không nhất quán

MongoDB BSON có int32, int64, double và Decimal128. Trong báo cáo tiền tệ:

- Nếu tiền được lưu ở đơn vị nhỏ nhất dưới dạng integer, chú ý miền giá trị và overflow.
- Nếu dùng Decimal128, chuẩn hóa inputs và quy tắc làm tròn.
- Tránh trộn các giá trị số và string rồi dựa vào coercion không được định nghĩa theo hợp đồng dữ liệu.
- Một tổng lũy kế có thể tăng lớn hơn giá trị của từng document; cần chọn kiểu dữ liệu phù hợp.

---

## 18. Sai lầm về `$match` trước và sau phân tích cửa sổ

### 18.1. Lọc trước sẽ thay **tập dữ liệu được tích lũy**

Giả sử muốn running total của HCM **kể từ đầu tháng**, nhưng API chỉ hiển thị các giao dịch từ ngày 02/01.

Nếu viết:

~~~javascript
db.sales.aggregate([
  {
    $match: {
      store: "HCM",
      day: {
        $gte: ISODate("2026-01-02T00:00:00Z")
      }
    }
  },
  {
    $setWindowFields: {
      partitionBy: "$store",
      sortBy: { day: 1, _id: 1 },
      output: {
        runningRevenue: {
          $sum: "$revenue",
          window: {
            documents: ["unbounded", "current"]
          }
        }
      }
    }
  },
  {
    $sort: { day: 1, _id: 1 }
  }
]);
~~~

thì giao dịch ID 1 của ngày 01/01 đã bị bỏ trước khi tính. Running total của ID 2 trở thành **200**, thay vì **300** nếu muốn lũy kế từ đầu tháng.

### 18.2. Lọc sau khi tính giữ lịch sử

~~~javascript
db.sales.aggregate([
  {
    $match: {
      store: "HCM"
    }
  },
  {
    $setWindowFields: {
      partitionBy: "$store",
      sortBy: { day: 1, _id: 1 },
      output: {
        runningRevenue: {
          $sum: "$revenue",
          window: {
            documents: ["unbounded", "current"]
          }
        }
      }
    }
  },
  {
    $match: {
      day: {
        $gte: ISODate("2026-01-02T00:00:00Z")
      }
    }
  },
  {
    $sort: { day: 1, _id: 1 }
  }
]);
~~~

Kết quả ID 2 có running total 300 vì ID 1 vẫn tham gia cửa sổ. `$match` ở cuối chỉ loại những document khỏi **output cuối**, không loại chúng khỏi lịch sử đã dùng tính toán.

### 18.3. Quy tắc thực hành

- `$match` theo **phạm vi nghiệp vụ phân tích** (tenant, store, loại sự kiện, tháng cần tính) nên ở trước window khi hợp lý.
- `$match` theo **tập kết quả muốn hiển thị** nhưng không muốn làm mất lịch sử lũy kế nên ở sau window.
- `$match` theo `rank <= N` đương nhiên phải ở sau stage tạo rank.
- Với dữ liệu cực lớn, tính lũy kế từ rất sớm có thể tốn kém; cân nhắc pre-aggregation hoặc snapshot số dư đầu kỳ thay vì phải quét vô hạn lịch sử.

Không chuyển `$match` qua lại chỉ vì muốn tối ưu scan nếu việc đó làm thay đổi ngữ nghĩa metric.

---

## 19. Phân vùng theo tenant, tháng và đơn vị nghiệp vụ

### 19.1. Thiếu `partitionBy` sẽ gộp toàn bộ input

Ví dụ:

~~~javascript
{
  $setWindowFields: {
    sortBy: { day: 1, _id: 1 },
    output: {
      runningRevenue: {
        $sum: "$revenue",
        window: {
          documents: ["unbounded", "current"]
        }
      }
    }
  }
}
~~~

Nếu không có `partitionBy`, toàn bộ input là **một partition**: doanh thu HCM và HN, DN có thể trộn vào một dãy lũy kế.

### 19.2. Partition theo tenant

Trong ứng dụng multi-tenant, nên giới hạn đúng tenant ngay từ filter/quyền truy cập và phân vùng theo đơn vị nghiệp vụ:

~~~javascript
db.sales.aggregate([
  {
    $match: {
      tenantId: "TENANT-01"
    }
  },
  {
    $setWindowFields: {
      partitionBy: "$store",
      sortBy: { day: 1, _id: 1 },
      output: {
        runningRevenue: {
          $sum: "$revenue",
          window: {
            documents: ["unbounded", "current"]
          }
        }
      }
    }
  }
]);
~~~

Đây là **ví dụ cấu trúc** cho collection có field `tenantId`; dữ liệu lab phần 3 không chứa field này. Trong production, filter quyền tenant là yêu cầu bảo mật riêng, không được trông cậy vào `partitionBy` để thay cơ chế phân quyền.

Nếu pipeline cho phép phân tích nhiều tenant một lúc, partition key cần bao gồm cả tenant để tránh gộp nhầm:

~~~javascript
partitionBy: {
  tenantId: "$tenantId",
  store: "$store"
}
~~~

### 19.3. Partition theo tháng: có reset lũy kế hàng tháng không?

Nếu doanh thu cần reset đầu mỗi tháng, tạo `saleMonth` bằng `$dateTrunc`:

~~~javascript
db.sales.aggregate([
  {
    $set: {
      saleMonth: {
        $dateTrunc: {
          date: "$day",
          unit: "month",
          timezone: "Asia/Ho_Chi_Minh"
        }
      }
    }
  },
  {
    $setWindowFields: {
      partitionBy: {
        store: "$store",
        month: "$saleMonth"
      },
      sortBy: { day: 1, _id: 1 },
      output: {
        monthlyRunningRevenue: {
          $sum: "$revenue",
          window: {
            documents: ["unbounded", "current"]
          }
        }
      }
    }
  },
  {
    $sort: {
      store: 1,
      saleMonth: 1,
      day: 1,
      _id: 1
    }
  }
]);
~~~

Giờ phân vùng là **cửa hàng + tháng**, nên lũy kế reset ở tháng mới. Nếu `day` là UTC và nghiệp vụ tính tháng theo Việt Nam, chỉ định timezone tránh nhầm các giao dịch gần nửa đêm UTC.

### 19.4. Dữ liệu thiếu partition key

Nếu field `store` thiếu hoặc null, nhiều document có thể bị gom chung vào một partition nullish theo cách biểu thức được xử lý. Không để báo cáo vô tình trộn các bản ghi không xác định cửa hàng với nhau.

Có thể:

- Lọc các document có store hợp lệ.
- Dùng `$ifNull` tạo một nhóm `"UNKNOWN_STORE"` để theo dõi.
- Từ chối dữ liệu sai schema tại API hoặc JSON Schema validation.
- Tạo báo cáo chất lượng dữ liệu riêng, không hòa lẫn vào kết quả tài chính chính thức.

---

## 20. Thứ tự phân tích cửa sổ và thứ tự hiển thị là hai chuyện khác nhau

### 20.1. Sort bên trong window phục vụ phép tính

~~~javascript
sortBy: {
  day: 1,
  _id: 1
}
~~~

chọn thứ tự để tính running total.

### 20.2. Sort cuối phục vụ UI

~~~javascript
{
  $sort: {
    store: 1,
    day: -1,
    _id: -1
  }
}
~~~

có thể khiến giao dịch mới nhất xuất hiện trước trên UI, **nhưng runningRevenue vẫn được tính theo thời gian tăng dần** ở stage trước.

Ví dụ HCM:

| Thứ tự hiển thị giảm dần | Revenue | Running từ đầu tháng |
|---:|---:|---:|
| ID 4 | 50 | 550 |
| ID 3 | 200 | 500 |
| ID 2 | 200 | 300 |
| ID 1 | 100 | 100 |

Đây không phải lỗi. Window sort định nghĩa cách tính, còn final sort định nghĩa cách trình bày.

### 20.3. Pagination phải cẩn thận

Nếu pipeline tính running total rồi `$skip` và `$limit` ở cuối, metric có thể vẫn đại diện cho toàn bộ lịch sử (đúng khi muốn hiển thị một trang của sổ cái lũy kế).

Nếu `$skip`/`$limit` đặt **trước** window, chỉ những document còn lại được tính. Khi đó trang 2 có thể reset running total tại đầu trang — thường sai với yêu cầu báo cáo từ đầu kỳ.

Với collection lớn, cần thiết kế pagination, checkpoint hoặc số dư đầu trang sao cho vừa đúng nghiệp vụ vừa không quá tốn tài nguyên.

---

## 21. Hiệu năng: sort, index, memory và disk spill

### 21.1. `$setWindowFields` có thể tốn kém

Window analytics cần có thứ tự và trạng thái partition. Với hàng triệu dòng:

- Cần xử lý sort theo `partitionBy`/`sortBy`.
- Có thể giữ thông tin của partition/window trong bộ nhớ.
- Một số cửa sổ unbounded hoặc rất rộng yêu cầu nhiều tài nguyên.
- Nhiều output operators hoặc nhiều `$setWindowFields` stages tăng chi phí tính toán.
- Dữ liệu phân bố lệch, một partition cực lớn, có thể trở thành nút thắt.

Cần đo workload thay vì giả định window operation giống một phép tính cộng đơn giản.

### 21.2. Chỉ số nên theo dõi

- Latency toàn pipeline và p95/p99.
- Số document vào `$setWindowFields`.
- Phân bố kích thước từng partition.
- Memory sử dụng và disk spill nếu có.
- Số key/document được duyệt ở các stage có index.
- CPU, disk I/O, server load và tác động tới query khác.
- Tốc độ ghi và nhu cầu làm mới read model.

### 21.3. `allowDiskUse`

Với các phiên bản/cấu hình hỗ trợ spill, có thể bật:

~~~javascript
db.sales.aggregate(
  [
    {
      $setWindowFields: {
        partitionBy: "$store",
        sortBy: { day: 1, _id: 1 },
        output: {
          runningRevenue: {
            $sum: "$revenue",
            window: {
              documents: ["unbounded", "current"]
            }
          }
        }
      }
    }
  ],
  {
    allowDiskUse: true
  }
);
~~~

**Không xem `allowDiskUse: true` là bảo đảm mọi pipeline sẽ chạy nhanh hoặc không có giới hạn tài nguyên.** Nó cho phép một số stage phù hợp sử dụng file tạm trên disk theo quy định server, có thể làm tăng I/O và latency.

Từ MongoDB 6.0, tham số `allowDiskUseByDefault` có thể thay đổi hành vi mặc định của một số stage cần nhiều bộ nhớ; các bản triển khai có thể khác theo cấu hình. Trong nhiều phiên bản, các stage có giới hạn bộ nhớ khoảng 100 MB theo các quy tắc tương ứng. Hãy đọc tài liệu của phiên bản MongoDB đang chạy, không suy từ một ngưỡng cố định cho mọi trường hợp.

### 21.4. Index hỗ trợ filter và sort

Giả sử truy vấn luôn lọc theo store và xếp thứ tự theo day/_id:

~~~javascript
db.sales.createIndex(
  {
    store: 1,
    day: 1,
    _id: 1
  },
  {
    name: "idx_sales_store_day_id"
  }
);
~~~

Index này có thể hỗ trợ những query shape sử dụng equality trên store và sort theo day/_id. Tuy nhiên, **không cam kết** MongoDB luôn dùng index đó cho mọi `$setWindowFields`; phải kiểm tra explain trên phiên bản và dataset thực tế.

Một pipeline:

~~~javascript
db.sales.aggregate([
  {
    $match: {
      store: "HCM"
    }
  },
  {
    $setWindowFields: {
      partitionBy: "$store",
      sortBy: { day: 1, _id: 1 },
      output: {
        runningRevenue: {
          $sum: "$revenue",
          window: {
            documents: ["unbounded", "current"]
          }
        }
      }
    }
  }
]);
~~~

Có thể tận dụng index để giảm chi phí một phần đường truy vấn, nhưng không thay thế việc đo sort, memory và window state.

### 21.5. Index cho rank khác index cho cumulative

Hai workload:

~~~javascript
// Running total
sortBy: {
  day: 1,
  _id: 1
}
~~~

~~~javascript
// Ranking
sortBy: {
  revenue: -1
}
~~~

không có cùng sort order. Một index tốt cho chạy lũy kế theo thời gian không nhất thiết tốt cho leaderboard theo doanh thu.

Tạo index bừa bãi cho mọi query sẽ tăng write amplification và dung lượng. Cần ưu tiên query shapes quan trọng nhất.

### 21.6. `explain`

~~~javascript
db.sales.explain("executionStats").aggregate([
  {
    $match: {
      store: "HCM"
    }
  },
  {
    $setWindowFields: {
      partitionBy: "$store",
      sortBy: { day: 1, _id: 1 },
      output: {
        runningRevenue: {
          $sum: "$revenue",
          window: {
            documents: ["unbounded", "current"]
          }
        }
      }
    }
  }
]);
~~~

Đọc winning plan, sort stages, index scans, document counts và các thống kê liên quan memory nếu phiên bản cung cấp. Hình dạng explain của window stage thay đổi theo phiên bản và engine; không viết script giả định một đường JSON cố định.

---

## 22. Báo cáo lớn: khi nào nên pre-aggregate hoặc materialize?

### 22.1. Bài toán doanh thu hàng ngày

Một cửa hàng có hàng triệu giao dịch trong 5 năm. Dashboard chỉ cần biểu đồ **doanh thu lũy kế theo ngày**, không cần từng transaction.

Dùng trực tiếp window trên toàn bộ các transaction có thể tốn nhiều công. Một chiến lược khác:

1. `$group` để cộng doanh thu theo **store + day**.
2. `$setWindowFields` trên các document doanh thu **ngày**.
3. Tính running total trên vài nghìn ngày thay vì hàng triệu transaction.
4. Chọn cách lưu/cập nhật bản tổng hợp phù hợp với hệ thống.

### 22.2. Pipeline hai tầng

~~~javascript
db.sales.aggregate([
  {
    $match: {
      revenue: {
        $type: "number"
      }
    }
  },
  {
    $group: {
      _id: {
        store: "$store",
        day: "$day"
      },
      dailyRevenue: {
        $sum: "$revenue"
      },
      dailyTransactions: {
        $sum: 1
      }
    }
  },
  {
    $set: {
      store: "$_id.store",
      day: "$_id.day"
    }
  },
  {
    $setWindowFields: {
      partitionBy: "$store",
      sortBy: {
        day: 1
      },
      output: {
        cumulativeDailyRevenue: {
          $sum: "$dailyRevenue",
          window: {
            documents: ["unbounded", "current"]
          }
        }
      }
    }
  },
  {
    $sort: {
      store: 1,
      day: 1
    }
  },
  {
    $project: {
      _id: 0,
      store: 1,
      day: 1,
      dailyRevenue: 1,
      dailyTransactions: 1,
      cumulativeDailyRevenue: 1
    }
  }
]);
~~~

Với HCM, hai giao dịch 02/01 được gộp thành dailyRevenue = 400. Kết quả ngày:

| Ngày | Daily revenue | Cumulative |
|---|---:|---:|
| 01/01 | 100 | 100 |
| 02/01 | 400 | 500 |
| 04/01 | 50 | 550 |

**Không áp dụng cách này nếu sản phẩm cần running total đến từng transaction**, vì `$group` đã gộp các giao dịch cùng ngày.

### 22.3. Materialized aggregate và số dư đầu kỳ

Nếu dashboard đọc liên tục, có thể lưu collection `daily_sales_summary` theo store/day, rồi chạy window trên collection đã tổng hợp. Khi dữ liệu cũ bị chỉnh, cần cập nhật lại ngày liên quan và các giá trị lũy kế phụ thuộc nếu được materialize.

Một cách khác cho sổ cái lớn:

- Lưu **opening balance** đầu kỳ hoặc checkpoint.
- Tính window chỉ trên phần giao dịch sau checkpoint.
- Cộng checkpoint với running sum trong kỳ.

Thiết kế này giảm khối lượng scan lịch sử, nhưng yêu cầu xử lý backdated events, sửa/xóa giao dịch và nhất quán checkpoint cẩn thận.

---

## 23. Đọc và ghi: aggregation không tự cập nhật collection

`$setWindowFields` trong:

~~~javascript
db.sales.aggregate([
  {
    $setWindowFields: {
      partitionBy: "$store",
      sortBy: { day: 1, _id: 1 },
      output: {
        runningRevenue: {
          $sum: "$revenue",
          window: {
            documents: ["unbounded", "current"]
          }
        }
      }
    }
  }
]);
~~~

thường tạo **kết quả đọc**. Nó **không tự ghi** field runningRevenue xuống các document trong `sales`.

Nếu muốn materialize, cân nhắc một pipeline với stage ghi thích hợp như `$merge` và quy trình vận hành riêng, nhưng phải xác định:

- Khóa duy nhất của bản tổng hợp.
- Khi nào recompute.
- Dữ liệu lịch sử bị chỉnh thì các running totals phía sau có đổi không?
- Các writer đồng thời và transaction/read concern.
- Chiến lược kiểm tra/rollback.
- Index trên collection đích.
- Quy tắc idempotency.

Không tự dùng `updateMany` với một biểu thức window như thể mọi update pipeline đều cho phép `$setWindowFields`. Window analytics là aggregation stage có phạm vi và hạn chế riêng; muốn lưu kết quả phải thiết kế pipeline ghi phù hợp.

---

## 24. Một số operator bổ trợ đáng biết

Mặc dù bài tập trung vào rank và cumulative sum, `$setWindowFields` còn hỗ trợ nhiều window operators khác:

| Operator | Tình huống |
|---|---|
| `$avg` | Moving average của doanh thu, nhiệt độ |
| `$min` / `$max` | Giá trị nhỏ nhất/lớn nhất trong window |
| `$count` | Số document trong window |
| `$first` / `$last` | Giá trị đầu/cuối trong window |
| `$push` | Danh sách các giá trị trong window |
| `$stdDevPop` / `$stdDevSamp` | Độ biến động |
| `$shift` | Lấy giá trị từ dòng trước/sau trong partition |
| `$expMovingAvg` | Trung bình động theo trọng số giảm dần |
| `$derivative` / `$integral` | Biến thiên hoặc tích lũy theo thời gian trong các trường hợp được hỗ trợ |

Các operator có điều kiện về version, sortBy, window và kiểu dữ liệu; không giả định mọi operator có cùng cú pháp.

### 24.1. So sánh với doanh thu giao dịch trước bằng `$shift`

Ví dụ:

~~~javascript
db.sales.aggregate([
  {
    $setWindowFields: {
      partitionBy: "$store",
      sortBy: {
        day: 1,
        _id: 1
      },
      output: {
        previousRevenue: {
          $shift: {
            output: "$revenue",
            by: -1,
            default: null
          }
        }
      }
    }
  },
  {
    $set: {
      revenueChange: {
        $cond: {
          if: {
            $and: [
              { $isNumber: "$revenue" },
              { $isNumber: "$previousRevenue" }
            ]
          },
          then: {
            $subtract: [
              "$revenue",
              "$previousRevenue"
            ]
          },
          else: null
        }
      }
    }
  },
  {
    $sort: {
      store: 1,
      day: 1,
      _id: 1
    }
  }
]);
~~~

`$shift` cũng dùng implicit window và **không nhận `window`**. Giá trị `by:-1` lấy dòng trước; ở đầu partition trả default null. Dùng `$cond` để tránh tính chênh lệch khi một trong hai giá trị không phải number.

### 24.2. Không lạm dụng tất cả operator cùng lúc

Một pipeline chỉ cần running sum không nhất thiết phải tính cả rank, denseRank, documentNumber, rolling average và shift. Mỗi output có chi phí; hãy triển khai đúng thông tin người dùng thực sự cần.

---

## 25. Ví dụ Java Sync Driver với pipeline window

Các ứng dụng Java có thể xây aggregation pipeline bằng `Document` hoặc builders phù hợp phiên bản driver.

Ví dụ tạo running total theo store:

~~~java
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.Arrays;
import java.util.List;

public class RunningRevenueExample {

    public static void run(MongoCollection<Document> sales) {

        Document window = new Document(
            "documents",
            Arrays.asList("unbounded", "current")
        );

        Document runningSum = new Document(
            "$sum",
            "$revenue"
        ).append(
            "window",
            window
        );

        Document output = new Document(
            "runningRevenue",
            runningSum
        );

        Document spec = new Document(
            "partitionBy",
            "$store"
        ).append(
            "sortBy",
            new Document("day", 1).append("_id", 1)
        ).append(
            "output",
            output
        );

        Bson windowStage = new Document(
            "$setWindowFields",
            spec
        );

        Bson finalSort = new Document(
            "$sort",
            new Document("store", 1)
                .append("day", 1)
                .append("_id", 1)
        );

        List<Bson> pipeline = Arrays.asList(
            windowStage,
            finalSort
        );

        sales.aggregate(pipeline)
            .forEach(System.out::println);
    }
}
~~~

Trong ví dụ:

- `sales` là `MongoCollection<Document>` đã được lấy từ một kết nối hợp lệ.
- `Document("$setWindowFields",spec)` diễn đạt cùng cấu trúc MQL như mongosh.
- `windowStage` không tự ghi dữ liệu; `aggregate()` trả kết quả.
- Driver không tự sửa sai kiểu revenue; đảm bảo schema hoặc conversion trước khi tính.
- Khi kết quả lớn, đừng gọi `into(new ArrayList<>())` một cách mù quáng vì có thể tốn nhiều RAM; streaming cursor/batch size theo workload sẽ phù hợp hơn.

### 25.1. Java leaderboard

Có thể xây output:

~~~java
Document rankOutput = new Document(
    "competitionRank",
    new Document("$rank", new Document())
).append(
    "denseRank",
    new Document("$denseRank", new Document())
);

Document rankSpec = new Document(
    "partitionBy",
    "$store"
).append(
    "sortBy",
    new Document("revenue", -1)
).append(
    "output",
    rankOutput
);

Bson rankStage = new Document(
    "$setWindowFields",
    rankSpec
);
~~~

Khi dùng `$rank` và `$denseRank`, **không thêm `window`** trong các output đó.

### 25.2. Thiết kế DTO

Nếu đầu ra gồm revenue Decimal128 và rank dạng số nguyên, DTO nên phản ánh kiểu dữ liệu thực. Tránh deserialize mọi giá trị thành string rồi tính toán lại trong Java.

Ví dụ một JSON response minh họa:

~~~json
{
  "store": "HCM",
  "seller": "Bình",
  "revenue": 200,
  "competitionRank": 1,
  "denseRank": 1
}
~~~

Đây là schema trình bày của ứng dụng, không phải cam kết kiểu JSON serialization của BSON Decimal128 trên mọi driver.

---

## 26. Các lỗi thường gặp và cách sửa

### Lỗi 1 — Quên `partitionBy` khi cần tích lũy riêng

**Dấu hiệu:** Tổng lũy kế của HCM có cả doanh thu HN.

**Nguyên nhân:** Bỏ `partitionBy` khiến toàn bộ input trở thành một partition.

**Sửa:** Thêm partition key đúng đơn vị nghiệp vụ, có thể gồm tenant/store/month.

### Lỗi 2 — Bỏ `window` rồi nhận tổng toàn nhóm

**Dấu hiệu:** Mọi dòng HCM đều có total 550 thay vì 100, 300, 500, 550.

**Nguyên nhân:** Với operator hỗ trợ, window mặc định chứa toàn partition.

**Sửa:** Dùng `documents:["unbounded","current"]` cho cumulative.

### Lỗi 3 — Rank trùng hạng nhưng mong muốn số thứ tự riêng

**Dấu hiệu:** Hai seller có rank 1 và không có rank 2.

**Nguyên nhân:** `$rank` giữ tie và bỏ số hạng sau tie.

**Sửa:** Nếu cần hạng không có gap, dùng `$denseRank`. Nếu cần số thứ tự từng dòng, dùng `$documentNumber`.

### Lỗi 4 — Dùng `$denseRank` nhưng kỳ vọng quy tắc competition rank

**Dấu hiệu:** Sau hai người cùng hạng 1, người kế tiếp có hạng 2 thay vì hạng 3.

**Nguyên nhân:** `$denseRank` không tạo gap.

**Sửa:** Dùng `$rank` nếu nghiệp vụ yêu cầu competition rank.

### Lỗi 5 — Thêm `_id` vào `sortBy` của `$rank`

**Dấu hiệu:** Lỗi do sortBy không hợp lệ hoặc làm thay đổi logic tie.

**Nguyên nhân:** Rank operators yêu cầu một sort field.

**Sửa:** Rank theo một metric; thêm final `$sort` với `_id` nếu muốn hiển thị ổn định. Dùng `$documentNumber` cho số dòng duy nhất.

### Lỗi 6 — Đặt `window` cho `$rank`

**Dấu hiệu:** Aggregation báo lỗi.

**Nguyên nhân:** `$rank`, `$denseRank` và `$documentNumber` có implicit window và không chấp nhận `window`.

**Sửa:** Bỏ `window` khỏi output của các rank operators.

### Lỗi 7 — Tưởng `sortBy` trong stage đảm bảo thứ tự output

**Dấu hiệu:** Kết quả đôi lúc không đúng thứ tự UI mong muốn.

**Nguyên nhân:** `$setWindowFields` không bảo đảm thứ tự document được trả.

**Sửa:** Thêm `$sort` cuối.

### Lỗi 8 — Hai giao dịch cùng timestamp làm running total khó dự đoán

**Dấu hiệu:** Số lũy kế theo từng dòng thay đổi vị trí giữa những dòng cùng ngày.

**Nguyên nhân:** Sort keys chưa định nghĩa thứ tự toàn phần.

**Sửa:** Dùng `sortBy:{day:1,_id:1}` hoặc khóa sequence nghiệp vụ.

### Lỗi 9 — Dùng `documents` để tính theo ngày

**Dấu hiệu:** "3 ngày gần nhất" lại chỉ có 3 giao dịch gần nhất, bỏ các giao dịch khác cùng ngày.

**Nguyên nhân:** `documents` dùng vị trí, không dùng thời gian.

**Sửa:** Dùng time `range` với `unit:"day"` khi yêu cầu theo lịch/giá trị thời gian.

### Lỗi 10 — Dùng range với nhiều sort fields

**Dấu hiệu:** Aggregation không hợp lệ.

**Nguyên nhân:** Range/time range window yêu cầu một sortBy field, tăng dần.

**Sửa:** Dùng một trường numeric/date cho range; nếu cần nhiều khóa để xác định thứ tự dòng, dùng documents window.

### Lỗi 11 — Lọc ngày trước window khiến tổng bị reset

**Dấu hiệu:** Running total từ đầu tháng thiếu doanh thu của các ngày đầu.

**Nguyên nhân:** `$match` trước window đã loại lịch sử cần dùng.

**Sửa:** Lọc theo store/tenant trước, tính window, sau đó lọc khoảng ngày chỉ phục vụ hiển thị; hoặc dùng opening balance hợp lệ.

### Lỗi 12 — Rank giao dịch khi cần rank seller

**Dấu hiệu:** Một seller có nhiều dòng và nhiều hạng.

**Nguyên nhân:** Chưa `$group` về một document trên mỗi seller trước khi rank.

**Sửa:** Group theo seller/store/time bucket rồi rank kết quả tổng hợp.

### Lỗi 13 — Coi null/missing revenue là 0 hợp lệ

**Dấu hiệu:** Báo cáo không phát hiện records thiếu doanh thu.

**Nguyên nhân:** `$sum` không cộng các giá trị không phải number; tổng có thể bằng 0.

**Sửa:** Thêm `invalidCount`/`validRevenueCount` hoặc schema validation.

### Lỗi 14 — Trộn string-number và number khi ranking

**Dấu hiệu:** Thứ hạng không phản ánh thứ tự tiền tệ.

**Nguyên nhân:** BSON type comparison hoặc dữ liệu sai kiểu.

**Sửa:** Chuẩn hóa numeric type, dùng `$convert` có `onError` và xử lý lỗi data quality.

### Lỗi 15 — Muốn Top N dòng nhưng dùng `$rank <= N`

**Dấu hiệu:** Nhận nhiều hơn hoặc ít hơn N dòng do tie.

**Nguyên nhân:** `$rank` biểu diễn hạng, không phải số thứ tự riêng của từng dòng.

**Sửa:** Dùng `$documentNumber` với sort deterministic nếu cần chính xác N rows.

### Lỗi 16 — Quá nhiều dữ liệu trong một partition

**Dấu hiệu:** Query tốn nhiều memory, spill hoặc chậm.

**Nguyên nhân:** Partition quá lớn, sort và các window operators phải xử lý nhiều document.

**Sửa:** Chọn phạm vi thời gian đúng, pre-aggregate, dùng index phù hợp, kiểm soát spill và benchmark.

### Lỗi 17 — Dùng `allowDiskUse` rồi cho rằng không có vấn đề

**Dấu hiệu:** Query vẫn chậm hoặc tốn nhiều I/O.

**Nguyên nhân:** Spilling là cơ chế hỗ trợ tài nguyên, không phải phép tối ưu vô điều kiện.

**Sửa:** Đo kích thước partition, stage costs, memory, sort và dữ liệu trung gian.

### Lỗi 18 — Nhầm read aggregation với update

**Dấu hiệu:** Chạy pipeline thấy runningRevenue trong kết quả nhưng collection không có field đó.

**Nguyên nhân:** `aggregate()` chỉ đọc/biến đổi dữ liệu trả về, trừ các pipeline có stage ghi được hỗ trợ và dùng có chủ đích.

**Sửa:** Nếu muốn lưu, thiết kế materialization với `$merge` và quy trình cập nhật/đối soát riêng.

---

## 27. Bài tập thực hành

### Bài tập 1 — Running total theo cửa hàng

Dùng collection `sales`:

1. Viết `$setWindowFields` partition theo store.
2. Sort theo day tăng, _id tăng.
3. Tính runningRevenue từ đầu partition tới dòng hiện tại.
4. Thêm final `$sort` để quan sát.
5. Kiểm tra HCM nhận 100, 300, 500, 550; HN nhận 150, 300, 600.

### Bài tập 2 — Quên window sẽ gây điều gì?

Viết lại bài 1 nhưng bỏ `window` của `$sum`. Dự đoán tại sao HCM mọi dòng có 550. Chứng minh sự khác nhau giữa full partition total và cumulative.

### Bài tập 3 — Xếp hạng có tie

Chỉ xếp hạng document có revenue numeric:

- `partitionBy:"$store"`.
- `sortBy:{revenue:-1}`.
- Cùng lúc xuất `competitionRank` và `denseRank`.

Giải thích hạng của HCM revenue 200,200,100,50 và HN revenue 300,150,150.

### Bài tập 4 — Chính xác hai dòng mỗi store

Dùng `$documentNumber` với sortBy revenue giảm, _id tăng và chỉ giữ `rowNumber <= 2`. So số lượng kết quả với `$rank <= 2` khi có tie.

### Bài tập 5 — Top 2 mức doanh thu

Dùng `$denseRank <= 2`. HCM trả những doanh thu nào? HN trả bao nhiêu dòng? Giải thích vì sao kết quả khác top 2 rows.

### Bài tập 6 — Moving sum của ba giao dịch

Dùng `documents:[-2,0]`, tính tổng và trung bình revenue trên tối đa ba dòng gần nhất của HCM. Tính bằng tay kết quả tại _id 4.

### Bài tập 7 — Hai ngày và ba giao dịch khác nhau thế nào?

Dùng `range:[-2,"current"],unit:"day"`. Tính doanh thu time range cho hai document HCM ngày 02/01 và document ngày 04/01. So với `documents:[-2,0]`.

### Bài tập 8 — Phần trăm lũy kế

Trong cùng stage tính runningRevenue và storeRevenue (full partition), sau đó tính runningSharePercent. Xử lý DN total = 0 sao cho không chia cho 0.

### Bài tập 9 — Missing và null

Dùng `$type`, `$isNumber`, `$cond`:

- Đếm những document revenue numeric theo từng partition.
- Đếm null/missing/invalid theo thứ tự lũy kế.
- Giải thích vì sao DN có runningRevenue 0 nhưng vẫn có lỗi dữ liệu.

### Bài tập 10 — Filter trước hoặc sau window

Muốn hiển thị HCM từ 02/01 nhưng tổng từ 01/01. Viết hai pipeline có `$match` khác vị trí. Chỉ ra nơi runningRevenue của _id 2 là 200 và nơi là 300.

### Bài tập 11 — Leaderboard seller tháng

Thêm nhiều transactions cho cùng seller, nhiều tháng. Dùng `$dateTrunc` theo timezone "Asia/Ho_Chi_Minh", `$group` doanh thu theo store/month/seller, sau đó `$denseRank` theo sellerRevenue giảm.

### Bài tập 12 — Thêm giao dịch cùng timestamp

Insert document HCM mới với day bằng 02/01 nhưng _id khác. Chạy cumulative:

- Chỉ sortBy day.
- SortBy day và _id.

Giải thích vì sao chỉ cách thứ hai định nghĩa rõ running total theo dòng.

### Bài tập 13 — Java Driver

Viết Java `Document` pipeline tạo runningRevenue. Thêm một pipeline thứ hai cho rank. Đảm bảo không đặt `window` trong rank output. Đọc kết quả theo cursor thay vì tải toàn bộ dataset vào RAM.

### Bài tập 14 — Tối ưu dữ liệu lớn

Giả sử collection có 50 triệu transactions và chỉ cần revenue cumulative theo ngày:

1. Đề xuất index hỗ trợ tenant/store/day nếu workload phù hợp.
2. Dùng `$group` theo ngày trước window.
3. Đo explain, memory, spill và p95 latency.
4. Đề xuất materialized daily summary hoặc checkpoint.
5. Giải thích cách xử lý một transaction được ghi muộn về ngày cũ.

---

## 28. Câu hỏi ôn tập

1. `$setWindowFields` xuất hiện từ MongoDB version nào?
2. Khác biệt cốt lõi giữa `$group` và `$setWindowFields`?
3. `partitionBy` có tác dụng gì, và nếu bỏ thì sao?
4. `sortBy` dùng cho điều gì? Nó có cam kết thứ tự output cuối không?
5. Tại sao tổng lũy kế cần `documents:["unbounded","current"]`?
6. Nếu bỏ `window` với `$sum`, kết quả có ý nghĩa gì?
7. Biên `"current"` và `"unbounded"` có nghĩa gì?
8. `documents:[-2,0]` bao gồm những dòng nào?
9. `range:[-2,0]` khác `documents:[-2,0]` như thế nào?
10. Time range với `unit:"day"` có giới hạn nào về sortBy?
11. Vì sao hai document cùng ngày có thể cho cùng time-range sum nhưng running sum theo dòng khác nhau?
12. `$rank` và `$denseRank` khác nhau ở việc bỏ hạng thế nào?
13. `$documentNumber` khác hai rank operators ra sao?
14. Vì sao rank operators không nhận `window`?
15. `$rank` có thể dùng bao nhiêu sortBy fields?
16. Nếu muốn có tie nhưng output hiển thị ổn định, làm thế nào?
17. Nếu muốn đúng N dòng, nên dùng rank hay document number?
18. Tại sao cần `$group` trước nếu xếp hạng seller theo tổng doanh thu?
19. Vì sao `$match` trước window có thể làm running total thay đổi?
20. `$sum` xử lý null/missing ra sao và rủi ro nghiệp vụ là gì?
21. Điều gì thay đổi trong xử lý null/missing của rank kể từ MongoDB 8.0?
22. Tại sao string-number phải được chuẩn hóa trước ranking?
23. Khi nào nên dùng daily pre-aggregation trước window?
24. Những chi phí nào cần theo dõi khi một partition quá lớn?
25. Vì sao `allowDiskUse` không phải cách tối ưu hóa duy nhất?
26. Khi nào cần materialize kết quả và xử lý cập nhật lịch sử ra sao?
27. Làm sao phân biệt thứ tự dùng để tính window với thứ tự UI?
28. Vì sao không dùng `$skip`/`$limit` trước window nếu muốn tổng lũy kế toàn kỳ?

---

## 29. Tổng kết

`$setWindowFields` là một công cụ quan trọng của MongoDB Aggregation để tính chỉ số **trên từng document nhưng có tham chiếu đến những document khác trong cùng nhóm**.

- **`partitionBy`** quyết định phép tính được chia theo cửa hàng, tenant, seller hoặc kỳ thời gian nào.
- **`sortBy`** quyết định thứ tự phục vụ phân tích.
- **`output` và `window`** xác định phép tính và phạm vi mỗi dòng được nhìn thấy.
- **`$rank`** giữ đồng hạng và có thể bỏ số hạng tiếp theo.
- **`$denseRank`** giữ đồng hạng nhưng không bỏ số hạng.
- **`$documentNumber`** gán số thứ tự riêng cho từng document.
- **`$sum` với `documents:["unbounded","current"]`** tạo tổng lũy kế từ đầu partition đến dòng hiện tại.
- **`documents`** tính theo vị trí dòng; **`range`** tính theo giá trị numeric/date theo các quy tắc riêng.

Bốn thói quen quan trọng nhất khi triển khai:

1. **Định nghĩa rõ đơn vị phân tích**: giao dịch, nhân viên, cửa hàng, ngày hay tháng.
2. **Đảm bảo thứ tự có ý nghĩa**: tie-breaker cho running total theo dòng, giữ tie có chủ ý cho rank.
3. **Phân biệt dữ liệu đúng và missing/null/sai kiểu**, không lẫn doanh thu 0 với thiếu dữ liệu.
4. **Kiểm chứng cả kết quả và chi phí thực tế**: `$sort` cuối, explain, index, memory, disk spill và khả năng pre-aggregate.

Một pipeline window tốt không chỉ tạo ra bảng số đẹp. Nó phải trả lời đúng câu hỏi nghiệp vụ: **ai được xếp hạng theo quy tắc nào, tổng đang tích lũy trong phạm vi nào, và kết quả có ổn định/đáng tin khi dữ liệu tăng hoặc thay đổi hay không**.

## Tài liệu MongoDB chính thức tham khảo

- [MongoDB Manual — $setWindowFields](https://www.mongodb.com/docs/manual/reference/operator/aggregation/setWindowFields/)
- [MongoDB Manual — $rank](https://www.mongodb.com/docs/manual/reference/operator/aggregation/rank/)
- [MongoDB Manual — $denseRank](https://www.mongodb.com/docs/manual/reference/operator/aggregation/denseRank/)
- [MongoDB Manual — $documentNumber](https://www.mongodb.com/docs/manual/reference/operator/aggregation/documentNumber/)
- [MongoDB Manual — $sum](https://www.mongodb.com/docs/manual/reference/operator/aggregation/sum/)
- [MongoDB Manual — $avg](https://www.mongodb.com/docs/manual/reference/operator/aggregation/avg/)
- [MongoDB Manual — $count (window expression)](https://www.mongodb.com/docs/manual/reference/operator/aggregation/count-accumulator/)
- [MongoDB Manual — $shift](https://www.mongodb.com/docs/manual/reference/operator/aggregation/shift/)
- [MongoDB Manual — $dateTrunc](https://www.mongodb.com/docs/manual/reference/operator/aggregation/dateTrunc/)
- [MongoDB Manual — $convert](https://www.mongodb.com/docs/manual/reference/operator/aggregation/convert/)
- [MongoDB Manual — Aggregation Pipeline Optimization](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-optimization/)
- [MongoDB Manual — Aggregation Pipeline Limits](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-limits/)
- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Manual — MongoDB 8.0 Compatibility Changes](https://www.mongodb.com/docs/manual/release-notes/8.0-compatibility/)
- [MongoDB Java Sync Driver — Aggregation](https://www.mongodb.com/docs/drivers/java/sync/current/aggregation/)
