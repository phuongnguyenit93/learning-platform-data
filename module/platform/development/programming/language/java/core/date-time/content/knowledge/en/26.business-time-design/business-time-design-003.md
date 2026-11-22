# Local-Time Recurring Schedules Must Retain Time Zone and DST Policies

## 1. "Every day at 09:00" is a schedule rule

A recurring schedule such as "every day at 09:00 in Berlin" is not just an initial `Instant` plus a fixed duration forever. It has three minimal components:

- A date-selection rule, such as every day or every Monday.
- A nominal wall-clock time, such as `09:00`.
- A time zone with rules, such as `Europe/Berlin`.

The **nominal time** is the time requested by the user in the rule. The **execution instant** is the `Instant` determined for a specific date after applying the zone rules and the policy for special cases.

When a zone observes daylight saving time (DST), the same local time can:

1. Correspond to exactly one instant.
2. Not exist because the clock jumps forward.
3. Occur twice because the clock falls back.

Therefore, the schedule also needs a **DST policy** to decide what to do in the last two cases. Storing only the time and the zone name while leaving the behavior unexpressed can still produce results that differ from business expectations.

## 2. Distinguishing clock-based schedules from elapsed durations

| Contract | Core data | What is preserved |
| --- | --- | --- |
| Every day at 09:00 in zone | Date rule + `LocalTime` + `ZoneId` | Nominal time on the local calendar |
| Every exact 24 elapsed hours | Initial instant + `Duration` | Interval on the timeline |
| Once at a determined instant | `Instant` | A single absolute point in time |

All three have appropriate applications. What matters is choosing the right contract.

For example, in `Europe/Berlin` during the March 2024 transition, starting from 09:00 the previous day:

- Adding exactly 24 elapsed hours yields 10:00 on the next day on the local clock.
- Selecting the next date and keeping 09:00 yields 09:00 on the next day; the interval on the timeline is then only 23 hours.

Thus, `previousInstant.plus(Duration.ofDays(1))` expresses a 24-hour interval, which is insufficient to fulfill the promise of "the same local time every day."

`ZonedDateTime.plusDays(1)` uses calendar-day arithmetic, but it still has built-in rules for resolving gaps and overlaps. For a scheduler with explicit requirements, it is better to retain the nominal date and nominal time and resolve each occurrence, rather than letting the shifted time of a previous occurrence become the new rule.

## 3. ZoneId must be stored together with the recurrence rule

A `ZoneId` such as `Europe/Berlin` allows looking up offset rules by date and time. A `ZoneOffset` such as `+01:00` is only a fixed offset.

If a schedule is created in winter and only `+01:00` is stored, the system has discarded the information needed to know that the same zone can use a different offset on a future date.

| Stored data | Sufficient to preserve the intent "09:00 in Berlin every day"? |
| --- | --- |
| A single initial `Instant` | Not sufficient to reconstruct the local-time rule |
| `LocalTime 09:00` | Missing zone and date rule |
| `LocalTime 09:00 + offset +01:00` | Only describes a time at a fixed offset |
| Date rule + `LocalTime 09:00 + ZoneId Europe/Berlin + policies` | Expresses the local schedule intent |

Do not use `ZoneId.systemDefault()` if the schedule belongs to a zone chosen by a user or organizational unit. A server deployed in another zone must not silently change the meaning of the schedule.

Similarly, `Locale` only serves language/formatting and certain regional conventions; it does not replace `ZoneId`. A user reading a Vietnamese interface can still set a schedule in Berlin.

## 4. Using ZoneRules to identify the three cases

According to [ZoneRules](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/zone/ZoneRules.html), you can obtain the list of valid offsets for a `LocalDateTime`:

```java
LocalDateTime requested = nominalDate.atTime(nominalTime);
List<ZoneOffset> offsets =
        zone.getRules().getValidOffsets(requested);
```

For standard transitions:

| Offset count | State | Consequence |
| --- | --- | --- |
| `1` | Normal | There is one matching `Instant` |
| `0` | Gap | The requested time does not exist |
| `2` | Overlap | Two `Instant`s share that local time |

The examples below use the verified Java environment zone rule data for Berlin in 2024:

- On 31/03, local time jumps from 02:00 to 03:00. `02:30` does not exist.
- On 27/10, the hour from 02:00 to before 03:00 occurs twice. `02:30` can go with `+02:00` or `+01:00`.

Do not use `getOffset(LocalDateTime)` alone to conclude whether a time exists or is unique: that method has its own way of picking an appropriate offset when it is not unique. The `getValidOffsets` list makes business decisions explicit.

In the example code, an offset count outside `0/1/2` is explicitly rejected. Do not silently pick an offset when an implementation encounters a configuration outside the designed scope.

## 5. Policies when a time does not exist

[ZoneOffsetTransition](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/zone/ZoneOffsetTransition.html) provides the transition duration, the offsets before and after, and the boundaries of the transition. From this, dedicated policies can be implemented:

| Gap policy | For request 02:30 on 31/03/2024 in Berlin |
| --- | --- |
| Skip occurrence, `SKIP` | Do not generate an execution for that nominal date |
| Shift by gap duration, `SHIFT_BY_GAP` | Add the one-hour gap, resulting in 03:30 |
| Pick first valid instant after gap, `NEXT_VALID` | Results in 03:00 |
| Reject, `REJECT` | Report that the nominal time does not exist |

Shifting by the gap duration and picking the first valid instant are two different behaviors. Do not lump them under a single name like "auto-fix time" without specifying which one.

The transition duration should not be hardcoded to one hour. Zone rules can have transitions of other lengths; use `transition.getDuration()` to get the actual duration. An adjustment can also affect the date, not just minutes and hours.

Choosing a policy must depend on the type of task. For example, a schedule that requires the exact requested time may reject a nonexistent time; an operational schedule that accepts shifting may use one of the two shifting approaches. The Java API does not decide that tolerance level for you.

For the skip policy, the schedule generator must continue to the next nominal date. "This date has no occurrence" does not mean the entire schedule has ended.

## 6. Policies when a time occurs twice

For Berlin on 27/10/2024 at 02:30:

| Valid offset | Instant |
| --- | --- |
| `+02:00` | `2024-10-27T00:30:00Z` |
| `+01:00` | `2024-10-27T01:30:00Z` |

Both rows have the same local date and time, but they are two instants one hour apart.

You can choose:

- **Earlier occurrence on the timeline**: pick `00:30Z`.
- **Later occurrence on the timeline**: pick `01:30Z`.
- **Both**: generate two executions.
- **Reject**: require the configurator or business owner to specify explicitly.

Naming them `EARLIER_INSTANT`/`LATER_INSTANT` avoids confusion with numerical comparison of offsets. `+02:00` is numerically greater than `+01:00`, yet it produces the earlier UTC instant for the same local time in the example.

A "once per nominal day" schedule usually has to pick one of the two. If running both is chosen, these are two business-authorized occurrences, not a duplicate execution caused by the system. Deduplication mechanisms need to know that difference.

When searching for the next occurrence from `now`, if the earlier occurrence has passed while the later one has not yet arrived, each generated `Instant` must be evaluated individually. Do not discard the entire nominal date just because one candidate for that date is already in the past.

## 7. Do not let default behavior replace the business contract

[ZonedDateTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZonedDateTime.html) has default resolution rules: gaps are typically shifted forward by the gap duration; overlaps may retain the previous offset if valid or pick the earlier offset per API rules.

For `LocalDateTime.atZone(zone)` without a preferred offset, an overlap is resolved using the API's default choice. The method does not necessarily throw an error just because the local time is ambiguous.

Therefore, a short snippet that runs without error does not prove that the desired policy was applied:

```java
ZonedDateTime resolved = requested.atZone(zone);
```

If the contract genuinely chooses that exact behavior, it can be used once its meaning is established. If you need to skip, reject, pick the later occurrence, or run both, you must implement it explicitly.

`ZonedDateTime.ofStrict(local, offset, zone)` checks whether the local time and offset pair is valid in the zone. In the example, it is called after obtaining a valid offset or adjusting the time according to policy; do not use it to silently fix inputs.

## 8. Complete Java 17+ program

Save as `LocalRecurrenceDstDemo.java`. The program resolves occurrences on the specified dates; it does not create a timer process or execute an external task.

```java
import java.time.DateTimeException;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.zone.ZoneOffsetTransition;
import java.time.zone.ZoneRules;
import java.util.List;
import java.util.Objects;

public class LocalRecurrenceDstDemo {
    enum GapPolicy { SKIP, SHIFT_BY_GAP, NEXT_VALID, REJECT }
    enum OverlapPolicy { EARLIER_INSTANT, LATER_INSTANT, BOTH, REJECT }

    record DailySchedule(
            LocalTime nominalTime,
            ZoneId zone,
            GapPolicy gapPolicy,
            OverlapPolicy overlapPolicy) {

        DailySchedule {
            Objects.requireNonNull(nominalTime);
            Objects.requireNonNull(zone);
            Objects.requireNonNull(gapPolicy);
            Objects.requireNonNull(overlapPolicy);
        }

        List<Instant> occurrencesOn(LocalDate nominalDate) {
            Objects.requireNonNull(nominalDate);
            LocalDateTime local = nominalDate.atTime(nominalTime);
            ZoneRules rules = zone.getRules();
            List<ZoneOffset> offsets = rules.getValidOffsets(local);

            if (offsets.size() == 1) {
                return List.of(ZonedDateTime.ofStrict(
                        local, offsets.get(0), zone).toInstant());
            }

            if (offsets.isEmpty()) {
                ZoneOffsetTransition transition = rules.getTransition(local);
                if (transition == null || !transition.isGap()) {
                    throw new DateTimeException("Missing gap transition");
                }
                return switch (gapPolicy) {
                    case SKIP -> List.of();
                    case NEXT_VALID -> List.of(transition.getInstant());
                    case SHIFT_BY_GAP -> {
                        LocalDateTime shifted = local.plusSeconds(
                                transition.getDuration().getSeconds());
                        yield List.of(ZonedDateTime.ofStrict(
                                shifted, transition.getOffsetAfter(), zone)
                                .toInstant());
                    }
                    case REJECT -> throw new DateTimeException(
                            "Nonexistent local time");
                };
            }

            if (offsets.size() != 2) {
                throw new DateTimeException("Unexpected offset count");
            }
            List<Instant> candidates = offsets.stream()
                    .map(offset -> ZonedDateTime.ofStrict(
                            local, offset, zone).toInstant())
                    .sorted()
                    .toList();

            return switch (overlapPolicy) {
                case EARLIER_INSTANT -> List.of(candidates.get(0));
                case LATER_INSTANT -> List.of(candidates.get(1));
                case BOTH -> candidates;
                case REJECT -> throw new DateTimeException(
                        "Ambiguous local time");
            };
        }
    }

    public static void main(String[] args) {
        ZoneId berlin = ZoneId.of("Europe/Berlin");
        LocalTime time = LocalTime.of(2, 30);
        DailySchedule shifted = new DailySchedule(
                time, berlin, GapPolicy.SHIFT_BY_GAP,
                OverlapPolicy.EARLIER_INSTANT);

        LocalDate first = LocalDate.of(2024, 3, 30);
        for (int index = 0; index < 3; index++) {
            LocalDate nominalDate = first.plusDays(index);
            for (Instant occurrence : shifted.occurrencesOn(nominalDate)) {
                System.out.println("daily " + nominalDate + " -> "
                        + occurrence.atZone(berlin));
            }
        }

        LocalDate gapDate = LocalDate.of(2024, 3, 31);
        System.out.println("gap skip = " + new DailySchedule(
                time, berlin, GapPolicy.SKIP,
                OverlapPolicy.EARLIER_INSTANT).occurrencesOn(gapDate));
        System.out.println("gap next valid = " + new DailySchedule(
                time, berlin, GapPolicy.NEXT_VALID,
                OverlapPolicy.EARLIER_INSTANT).occurrencesOn(gapDate));

        LocalDate overlapDate = LocalDate.of(2024, 10, 27);
        for (OverlapPolicy policy : List.of(
                OverlapPolicy.EARLIER_INSTANT,
                OverlapPolicy.LATER_INSTANT,
                OverlapPolicy.BOTH)) {
            DailySchedule schedule = new DailySchedule(
                    time, berlin, GapPolicy.REJECT, policy);
            System.out.println("overlap " + policy + " = "
                    + schedule.occurrencesOn(overlapDate));
        }

        try {
            new DailySchedule(time, berlin, GapPolicy.REJECT,
                    OverlapPolicy.REJECT).occurrencesOn(gapDate);
        } catch (DateTimeException ex) {
            System.out.println("gap reject = " + ex.getMessage());
        }

        ZonedDateTime morning = LocalDate.of(2024, 3, 30)
                .atTime(9, 0).atZone(berlin);
        System.out.println("plus 24 hours = "
                + morning.plus(Duration.ofHours(24)));
        System.out.println("plus one date day = " + morning.plusDays(1));
    }
}
```

Compile and run:

```shell
javac --release 17 LocalRecurrenceDstDemo.java
java LocalRecurrenceDstDemo
```

Verified stdout with the time-zone data of the Java environment in use:

```text
daily 2024-03-30 -> 2024-03-30T02:30+01:00[Europe/Berlin]
daily 2024-03-31 -> 2024-03-31T03:30+02:00[Europe/Berlin]
daily 2024-04-01 -> 2024-04-01T02:30+02:00[Europe/Berlin]
gap skip = []
gap next valid = [2024-03-31T01:00:00Z]
overlap EARLIER_INSTANT = [2024-10-27T00:30:00Z]
overlap LATER_INSTANT = [2024-10-27T01:30:00Z]
overlap BOTH = [2024-10-27T00:30:00Z, 2024-10-27T01:30:00Z]
gap reject = Nonexistent local time
plus 24 hours = 2024-03-31T10:00+02:00[Europe/Berlin]
plus one date day = 2024-03-31T09:00+02:00[Europe/Berlin]
```

`DailySchedule` stores `nominalTime` and `ZoneId` along with both policies. `occurrencesOn` returns a list because one date can yield `0`, `1`, or `2` occurrences depending on the policy:

- A gap with `SKIP` returns an empty list.
- Normal cases and single-occurrence policies return one element.
- An overlap with `BOTH` returns two `Instant`s sorted chronologically.

`NEXT_VALID` takes `transition.getInstant()`, which is the boundary where the post-transition offset takes effect. For the gap in the example, that is 03:00 local time, unlike `SHIFT_BY_GAP` which turns 02:30 into 03:30.

The methods and constructor validate required data; they do not fall back to the server's zone when `zone` is missing. The code uses fixed zones and dates so it can be verified without waiting for DST to occur in real time.

## 9. Preserving nominal time to prevent schedule drift

The first three lines of stdout are the key point:

```text
30/03: 02:30
31/03: 03:30 due to SHIFT_BY_GAP policy
01/04: 02:30
```

31/03 is shifted, but the original rule remains `02:30`. 01/04 is constructed from **new nominal date + original nominal time**, so it returns to `02:30`.

If you take the `ZonedDateTime` that was shifted to 03:30 and call `plusDays(1)` to generate the next occurrence, 03:30 may continue to be carried forward. The system would then have turned a single-day exception into a new schedule.

The recommended flow is:

1. Generate the nominal date from the recurrence rule.
2. Combine it with the nominal time.
3. Look up the zone rules for that exact date and time.
4. Apply the gap/overlap policy.
5. Pass the resulting `Instant`s to the execution mechanism.

For weekly schedules, the first step selects the right day of the week. For monthly schedules, the first step also needs a policy for nonexistent calendar dates, such as the 31st in a short month. Calendar-date policies and DST policies are two separate layers and should be described independently.

Do not update the original nominal time or zone just because one resolution had to be adjusted.

## 10. Data to store for a real-world schedule

A local-time schedule configuration typically needs:

| Data | Purpose |
| --- | --- |
| Schedule ID and configuration version | Identification and change auditing |
| Date-selection rule | Daily, weekly, monthly, etc. |
| Start/end date if applicable | Bounding the recurrence range |
| Nominal `LocalTime` | Preserving the local wall-clock intent |
| `ZoneId` string | Looking up zone rules |
| Gap policy | Handling nonexistent times |
| Overlap policy | Handling times that occur twice |
| Misfire / overdue task policy | Handling when the system did not run on time |

You can also store `nextFireInstant` for querying and queuing into the execution queue. However, this value is a **computed result** and should not be the sole replacement for the original rule.

When explaining an occurrence that ran, record the nominal date/time, the chosen offset, the actual instant, the schedule version, and the policy application result. An `Instant` tells when, but does not by itself explain why the task was scheduled at that time.

If the schedule follows a branch's fixed zone, retain that zone. If the schedule must follow the current zone in a user's profile, specify clearly when a zone change takes effect and how previously generated occurrences are handled; do not let profile updates silently alter pending occurrences without a rule.

## 11. DST policy differs from missed-task policy

02:30 not existing due to DST is a local-calendar issue. The system being shut down at 09:00 and restarted at 10:00 is a different operational issue.

For tasks that became due while the system was down, you may need to:

- Skip overdue occurrences.
- Run a single catch-up occurrence.
- Run catch-up for each occurrence within a window.
- Cap the number of catch-up runs to avoid piling up too many tasks.

These choices are not derived from `GapPolicy` or `OverlapPolicy`. A schedule with `SKIP` in a gap may still require catching up on a 09:00 task missed due to server downtime.

Similarly, choosing `BOTH` in an overlap does not authorize re-running the same occurrence indefinitely on retries. Each generated occurrence needs a distinct identifier, such as schedule ID + version + nominal position in the rule + overlap branch.

Persisting execution state and ensuring task side effects can handle retries as required are responsibilities of the execution mechanism. Computing the right `Instant` alone does not guarantee the task actually runs once.

## 12. Zone rules can be updated

Time-zone data provided by the Java environment can change when the vendor updates rules. A future zone-based schedule must account for this.

There are two distinct requirements:

- "Always follow the zone's local time using the latest rules used by the system."
- "Keep the confirmed instant for a specific occurrence unchanged."

For the first requirement, precomputed future occurrences may need to be recomputed when zone rules are updated. For the second requirement, retaining the confirmed `Instant` and its corresponding explanatory data may be necessary. Do not apply a single policy to every type of schedule.

Updates must consider already-executed occurrences, pending occurrences, and the schedule configuration. Do not recompute everything blindly and accidentally create duplicate occurrences or skip occurrences.

When auditing is needed, you can record the time-zone data version if the provider exposes it, along with the application version and schedule configuration. In verification tests, use known transition dates in the environment's dataset and check edge cases.

The 2024 Berlin examples in this article are data for observing verified behavior, not a claim that all zones will always transition on the same dates or with the same duration.

## 13. Edge cases that require further thought

An offset change does not have to be exactly one hour long. If an adjustment shifts across a date boundary, two different nominal dates can produce colliding results depending on the policy. The system must decide whether to run two occurrences, merge them, or reject that configuration.

When generating schedules in bulk, bound the date range or the number of occurrences to compute. Do not build an infinite list just to find the next occurrence. With the skip policy, continue scanning dates within an explicit bound.

When a schedule has an end date, define whether that bound applies to the nominal date or to the adjusted instant. An occurrence on the last day that gets shifted to the next day may be accepted or excluded under two different contracts.

The demonstration focuses on resolving one occurrence per day within a valid data domain. A complete scheduler must also manage bounds, out-of-domain inputs, configuration changes, and task state; the example record should not be treated as a complete scheduling system.

## 14. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Storing only an `Instant` and adding 24 hours | Local time can shift across DST | Retain date rule, nominal time, and zone |
| Storing only the initial offset | Loses zone transition rules | Retain `ZoneId` if intent is zone-based |
| Using the server's default zone | Schedule meaning changes by environment | Pass the zone from schedule configuration |
| Calling `atZone` and assuming every time is unique | Ignores default gap/overlap resolution rules | Define explicit policies |
| Shifting every gap by exactly one hour | Fails for transitions of other durations | Read `ZoneOffsetTransition` |
| Treating gap-shift as equivalent to first valid time | Wrong execution minute | Distinguish the two policies |
| Using the shifted time of the previous run as the base time | Schedule drifts over time | Recombine each day with `nominalTime` |
| Picking both overlap occurrences without a branch identifier | Hard to deduplicate properly | Identify each generated occurrence |
| Conflating DST with tasks missed due to system downtime | Wrong catch-up or skipping behavior | Separate operational policies |
| Ignoring time-zone data updates | Future occurrences may diverge from new intent | Have a clear recompute/pin policy |

## 15. Self-verification and practice

1. Run the example and explain why the 02:30 schedule is only shifted on the gap date, then returns to 02:30 on the next day.
2. Compare `SHIFT_BY_GAP` and `NEXT_VALID` for the same 02:30 request. One gives 03:30, the other gives 03:00.
3. Verify that `SKIP` returns an empty list while the schedule generation loop can still continue to the next day.
4. For overlap, verify that the two `Instant`s differ, yet when viewed in the zone both have local time 02:30.
5. Use `LATER_INSTANT` and confirm the selected occurrence is `01:30Z` in the example.
6. Test `REJECT` for both gap and overlap; the error must state the reason according to the contract.
7. Change the nominal time to 09:00. Compare the actual elapsed interval between two days across the transition against the "exact 24 hours" rule.
8. Describe the occurrence identifier key if the schedule chooses `BOTH` and the system needs to retry tasks.
9. Design a weekly schedule with an end date and state clearly whether the nominal date or the adjusted date is used to evaluate the bound.
10. Describe how to handle a user changing their zone or time-zone data being updated while future occurrences are already queued to run.

A local-time schedule must preserve the original intent along with zone rules and policies for nonexistent or non-unique times. The generated `Instant`s are outputs for execution; they do not replace the full meaning of the recurring schedule.
